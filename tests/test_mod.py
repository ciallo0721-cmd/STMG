# -*- coding: utf-8 -*-
"""美化包测试：离线手动安装、在线索引、下载安装、以及「坏包必须进不来」。

在线那部分不动真网络：索引和 zip 都写在 tmp_path 里，
fetch_index / install_from_url 本来就支持本地路径，测起来更稳。
"""

import hashlib
import json
import os
import shutil
import zipfile

from stmg import mod


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_PACK = os.path.join(HERE, "mod", "none")      # 拿默认包当模板造测试包


def make_pack(root, mid="testpack", name="测试包", extra=None):
    """在 root 下造一个合法的美化包目录，返回路径。"""
    dst = os.path.join(root, mid)
    shutil.copytree(BASE_PACK, dst)
    man_path = os.path.join(dst, "mod.json")
    with open(man_path, "r", encoding="utf-8") as f:
        man = json.load(f)
    man.update({"id": mid, "name": name})
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    for rel, content in (extra or {}).items():
        p = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    return dst


def make_zip(pack_dir, zip_path, arc_root=None):
    """把包目录压成「包名/...」结构的 zip（和 tools/modpub.py 的产物一致）。"""
    root = arc_root or os.path.basename(pack_dir)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for r, _, files in os.walk(pack_dir):
            for name in files:
                p = os.path.join(r, name)
                z.write(p, os.path.join(root, os.path.relpath(p, pack_dir)))
    return zip_path


def write_index(path, entries, folder=None):
    """写一个索引 JSON；url 写相对路径（引擎会按索引所在目录补全）。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mods": entries}, f, ensure_ascii=False)


def sha256_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_copy_mod_into_project(project):
    """离线安装：copy_mod 把包拷进项目的 mod/，重名时拒绝而不是覆盖。"""
    d, _ = project
    src = make_pack(d, "sakura", "樱花")
    dst = mod.copy_mod(src, d)
    assert os.path.isdir(dst)
    assert mod.active_id(d) in ("none", "sakura")
    issues = mod.verify(dst)
    assert not mod.errors_of(issues), mod.errors_of(issues)
    try:
        mod.copy_mod(src, d)
    except OSError as e:
        assert "已经有" in str(e)
    else:
        raise AssertionError("重名安装应该报错，不能默默覆盖")


def test_fetch_index_resolves_relative_urls(tmp_path):
    """索引里的相对地址要按索引自身目录补全，否则装的时候路径全错。"""
    folder = tmp_path / "repo"
    folder.mkdir()
    idx = folder / "index.json"
    write_index(idx, [{"id": "sakura", "name": "樱花", "url": "sakura_美化包.zip"}])
    entries, err = mod.fetch_index(str(idx))
    assert err == "", err
    assert len(entries) == 1
    assert os.path.basename(entries[0]["url"]) == "sakura_美化包.zip"
    assert os.path.dirname(entries[0]["url"]) == str(folder)


def test_fetch_index_reports_bad_json(tmp_path):
    """索引是坏 JSON 时返回中文错误文案，不抛异常。"""
    p = tmp_path / "index.json"
    p.write_text("{ 这不是 json", encoding="utf-8")
    entries, err = mod.fetch_index(str(p))
    assert entries == []
    assert "JSON" in err or "json" in err


def test_fetch_index_without_any_source(monkeypatch):
    """没配索引地址时给一句能看懂的话，而不是空列表。"""
    monkeypatch.setattr(mod, "MOD_INDEX_URL", "")
    entries, err = mod.fetch_index("")
    assert entries == [] and err


def test_install_from_index(project, tmp_path):
    """完整链路：索引 → 下载 → 校验 → 落地。落地后包必须能被 list_mods 看到。"""
    d, _ = project
    os.makedirs(os.path.join(d, "mod"), exist_ok=True)
    pack = make_pack(str(tmp_path), "sakura", "樱花")
    zp = make_zip(pack, str(tmp_path / "sakura_美化包.zip"))
    idx = tmp_path / "index.json"
    write_index(idx, [{"id": "sakura", "name": "樱花", "version": "1.0.0",
                       "url": "sakura_美化包.zip", "sha256": sha256_of(zp)}])

    entries, err = mod.fetch_index(str(idx))
    assert err == "", err
    ok, msg, mid = mod.install_from_url(entries[0]["url"], entries[0]["id"],
                                        entries[0]["sha256"], root=d)
    assert ok, msg
    assert mid == "sakura"
    ids = [m["id"] for m in mod.list_mods(d)]
    assert "sakura" in ids


def test_install_refuses_wrong_sha(project, tmp_path):
    """sha256 对不上（被截断 / 被换包）必须拒装。"""
    d, _ = project
    os.makedirs(os.path.join(d, "mod"), exist_ok=True)
    pack = make_pack(str(tmp_path), "sakura")
    zp = make_zip(pack, str(tmp_path / "sakura.zip"))
    ok, msg, _ = mod.install_from_url(zp, "sakura", "0" * 64, root=d)
    assert not ok and "校验" in msg
    assert not os.path.isdir(os.path.join(d, "mod", "sakura"))


def test_install_refuses_zip_slip(project, tmp_path):
    """zip 里带 ../ 的越界路径必须整包拒绝（不能写到项目外面去）。"""
    d, _ = project
    os.makedirs(os.path.join(d, "mod"), exist_ok=True)
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../逃出去.txt", "不该存在")
        z.writestr("sakura/mod.json", "{}")
    ok, msg, _ = mod.install_from_url(str(evil), "sakura", "", root=d)
    assert not ok and "越界" in msg
    assert not os.path.exists(os.path.join(d, "逃出去.txt"))


def test_install_refuses_executables(project, tmp_path):
    """美化包不许带 .exe / .bat / .dll —— 这条是安全底线，不能只靠发布时检查。"""
    d, _ = project
    os.makedirs(os.path.join(d, "mod"), exist_ok=True)
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("sakura/mod.json", "{}")
        z.writestr("sakura/run.exe", b"MZ")
    ok, msg, _ = mod.install_from_url(str(evil), "sakura", "", root=d)
    assert not ok
    assert ".exe" in msg or "不许" in msg


def test_install_refuses_pack_failing_verify(project, tmp_path):
    """能解压、但内容违规（比如 gui.py 里写函数）的包，校验不过就不能落地。"""
    d, _ = project
    os.makedirs(os.path.join(d, "mod"), exist_ok=True)
    pack = make_pack(str(tmp_path), "sakura", extra={
        "gui.py": "import os\nCONFIG = {}\n",
    })
    zp = make_zip(pack, str(tmp_path / "sakura.zip"))
    ok, msg, _ = mod.install_from_url(zp, "sakura", "", root=d)
    assert not ok and "校验" in msg
    assert not os.path.isdir(os.path.join(d, "mod", "sakura"))


def test_install_does_not_overwrite(project, tmp_path):
    """已装过的同名包不覆盖——用户手改过的东西不能被一次安装抹掉。"""
    d, _ = project
    os.makedirs(os.path.join(d, "mod"), exist_ok=True)
    pack = make_pack(str(tmp_path), "sakura")
    zp = make_zip(pack, str(tmp_path / "sakura.zip"))
    assert mod.install_from_url(zp, "sakura", "", root=d)[0]
    ok, msg, _ = mod.install_from_url(zp, "sakura", "", root=d)
    assert not ok and "已经装过" in msg
