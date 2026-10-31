# -*- coding: utf-8 -*-
"""生成美化包在线索引 index.json。

用法：
    python tools/modindex.py                       # 扫 dist/mods，产物写回 dist/mods/index.json
    python tools/modindex.py <目录> --out <文件>    # 指定扫描目录与输出路径
    python tools/modindex.py <目录> --base https://example.com/mods/

做的事：把目录下所有 `.zip` 挨个打开，读里面的 `mod.json` 清单，
算出 sha256 与体积，拼成引擎认的索引格式：

    {"mods": [
      {"id": "sakura", "name": "樱花", "version": "1.0.0", "author": "某人",
       "desc": "粉色系", "url": "sakura_美化包.zip", "sha256": "...", "size": 12345}
    ]}

url 默认写**相对路径**（相对索引文件自身），所以只要把 index.json 和 zip 放
同一个目录，传到任何静态托管上都能直接用。要写绝对地址就传 --base。

索引地址的三种给法（优先级从低到高）：
    环境变量 STMG_MOD_INDEX  >  mod/online.json 里的 {"index": "..."}  >  启动器里临时填
"""

import argparse
import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def read_manifest(zip_path, fallback_id):
    """从 zip 里找唯一一个 mod.json，返回 (id, 清单字典)。

    美化包可能是 `包名/mod.json`，也可能 mod.json 在 zip 根目录，两种都认。
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = [n for n in zf.namelist()
                     if n.replace("\\", "/").split("/")[-1] == "mod.json"]
            if not names:
                return fallback_id, {}
            # 层级最浅的那个才是包清单（避免读到嵌套的示例目录）
            names.sort(key=lambda n: n.count("/"))
            with zf.open(names[0]) as f:
                data = json.loads(f.read().decode("utf-8-sig"))
            mid = str((data or {}).get("id") or "").strip() or fallback_id
            return mid, (data if isinstance(data, dict) else {})
    except (OSError, ValueError, zipfile.BadZipFile):
        return fallback_id, {}


def build(folder, base=""):
    """扫一个目录下的 zip，返回索引字典。base 非空时 url 拼成绝对地址。"""
    mods = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(".zip"):
            continue
        p = os.path.join(folder, name)
        if not os.path.isfile(p):
            continue
        stem = os.path.splitext(name)[0]
        # 发布产物叫「樱花_美化包.zip」，去掉后缀当兜底 id
        fallback = stem[:-len("_美化包")] if stem.endswith("_美化包") else stem
        mid, man = read_manifest(p, fallback)
        with open(p, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        url = name if not base else base.rstrip("/") + "/" + name
        mods.append({
            "id": mid,
            "name": str(man.get("name") or fallback),
            "version": str(man.get("version") or "1.0.0"),
            "author": str(man.get("author") or "匿名"),
            "desc": str(man.get("desc") or ""),
            "url": url,
            "sha256": digest,
            "size": os.path.getsize(p),
        })
    return {"mods": mods}


def main(argv):
    """命令行入口：解析参数、扫目录、写 index.json。"""
    ap = argparse.ArgumentParser(description="生成美化包在线索引")
    ap.add_argument("folder", nargs="?", default=os.path.join(HERE, "dist", "mods"),
                    help="扫描哪个目录（默认 dist/mods）")
    ap.add_argument("--out", default="", help="输出文件（默认 <folder>/index.json）")
    ap.add_argument("--base", default="", help="zip 的绝对地址前缀，如 https://example.com/mods/")
    args = ap.parse_args(argv[1:])

    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        print("目录不存在：%s" % folder)
        return 2

    data = build(folder, args.base)
    out = os.path.abspath(args.out or os.path.join(folder, "index.json"))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("索引已生成：%s" % out)
    print("收录 %d 个美化包：" % len(data["mods"]))
    for m in data["mods"]:
        print("  %-16s %-12s %8.1f KB  %s"
              % (m["id"], m["version"], m["size"] / 1024.0, m["name"]))
    print("-" * 62)
    print("把 index.json 和这些 zip 一起传到任意静态托管，")
    print("再在 mod/online.json 里写 {\"index\": \"<index.json 的地址>\"} 就能一键装。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
