#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通过 GitHub API 推送当前分支，并自动对齐本地 ref。

为什么需要这个而不是直接 `git push`：
    github.com:443 在本机常年被 SNI 阻断（`Recv failure: Connection was reset`），
    但 api.github.com 通常可达。于是改用 Git Data API 手动拼 commit。

和 skill 里那个通用脚本的区别：**每个请求都带超时和重试**。
通用的那个在弱网下会挂在某个请求上十几分钟不动，这个最多重试 4 次、每次 45 秒。

用法：
    python tools/git_api_push.py            # 推 main
    python tools/git_api_push.py dev        # 推别的分支

推完会自动把远端 commit 对象按字节复刻进本地对象库并 update-ref，
所以 `git status` 不会出现「内容一样却 ahead 1 / behind 1」的假分叉。
"""
import base64
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

OWNER, NAME = "ciallo0721-cmd", "STMG"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCH = sys.argv[1] if len(sys.argv) > 1 else "main"
API = "https://api.github.com/repos/%s/%s" % (OWNER, NAME)

_raw = subprocess.run(
    "printf 'protocol=https\\nhost=github.com\\n\\n' | git credential fill",
    shell=True, capture_output=True, text=True, cwd=REPO).stdout
_token = [l.split("=", 1)[1] for l in _raw.splitlines() if l.startswith("password=")]
if not _token:
    raise SystemExit("凭据库里没有 github.com 的 token（git credential fill 拿不到）")
H = {"Authorization": "Bearer " + _token[0], "User-Agent": "stmg-push",
     "Accept": "application/vnd.github+json", "Content-Type": "application/json"}


def call(method, url, body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, data=data, headers=H, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code < 500:              # 4xx 是参数问题，重试没用
                return e.code, msg
            last = "HTTP %d %s" % (e.code, msg)
        except Exception as e:            # 超时 / SSL EOF / 连接重置
            last = repr(e)
        print("  重试 %d/%d (%s)" % (i + 1, tries, last))
        time.sleep(2 + i * 3)
    raise SystemExit("请求失败 %s %s -> %s" % (method, url, last))


def git(*args, **kw):
    return subprocess.run(["git"] + list(args), cwd=REPO, capture_output=True, **kw)


def align(remote):
    """把远端 commit 对象复刻进本地对象库，再把两个 ref 指过去。

    API 建的 commit 和本地 git commit 的字节不一样（尾部换行、时区），
    sha 必然不同 —— 但 tree 相同。复刻之后两边就是同一个对象。
    """
    st, c = call("GET", API + "/git/commits/" + remote)
    if st != 200:
        print("取远端 commit 失败，跳过对齐: %s" % c)
        return
    tree = c["tree"]["sha"]
    parent = c["parents"][0]["sha"] if c["parents"] else None

    def epoch(iso):
        return int(datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())

    ae, ce = epoch(c["author"]["date"]), epoch(c["committer"]["date"])
    body = c["message"].encode("utf-8")

    for tail in ("", "\n", "\n\n"):
        for tz in ("+0000", "+0800"):
            obj = ("tree %s\n" % tree).encode()
            if parent:
                obj += ("parent %s\n" % parent).encode()
            obj += ("author %s <%s> %d %s\ncommitter %s <%s> %d %s\n\n"
                    % (c["author"]["name"], c["author"]["email"], ae, tz,
                       c["committer"]["name"], c["committer"]["email"], ce, tz)).encode()
            obj += body.rstrip(b"\n") + tail.encode()
            if hashlib.sha1(b"commit %d\0" % len(obj) + obj).hexdigest() == remote:
                subprocess.run(["git", "hash-object", "-t", "commit", "-w", "--stdin"],
                               input=obj, cwd=REPO, check=True)
                subprocess.run(["git", "update-ref", "refs/heads/" + BRANCH, remote], cwd=REPO)
                subprocess.run(["git", "update-ref", "refs/remotes/origin/" + BRANCH, remote], cwd=REPO)
                print("已对齐（tz=%s tail=%r）" % (tz, tail))
                return
    print("警告：复刻字节没命中，本地会显示 ahead/behind（内容其实一致）")


def main():
    head = git("rev-parse", "HEAD").stdout.decode().strip()
    tree = git("rev-parse", "HEAD^{tree}").stdout.decode().strip()

    st, ref = call("GET", API + "/git/ref/heads/" + BRANCH)
    if st != 200:
        raise SystemExit("取 ref 失败: %s %s" % (st, ref))
    base = ref["object"]["sha"]
    print("本地 %s   远端 %s   分支 %s" % (head[:8], base[:8], BRANCH))
    if base == head:
        print("已经一致，无需推送")
        return 0

    st, base_commit = call("GET", API + "/git/commits/" + base)
    if st != 200:
        raise SystemExit("取远端 commit 失败: %s %s" % (st, base_commit))

    diff = git("diff", "--name-status", base, head).stdout.decode("utf-8").splitlines()
    changes = []
    for line in diff:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        if status.startswith("D"):
            changes.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
        else:
            changes.append({"path": path, "mode": "100644", "type": "blob",
                            "sha": git("rev-parse", "HEAD:" + path).stdout.decode().strip()})
    print("改动 %d 个文件" % len(changes))

    for c in changes:
        if c["sha"] is None:
            continue
        # 字节必须从对象库取：工作区可能被 autocrlf 转成 CRLF，推上去 sha 就对不上了
        raw = git("cat-file", "blob", c["sha"]).stdout
        st, r = call("POST", API + "/git/blobs",
                     {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
        if st not in (200, 201):
            raise SystemExit("传 blob 失败 %s: %s" % (c["path"], r))
        if r["sha"] != c["sha"]:
            raise SystemExit("blob sha 不一致 %s" % c["path"])
        print("  %-34s %8d B" % (c["path"], len(raw)))

    st, t = call("POST", API + "/git/trees",
                 {"base_tree": base_commit["tree"]["sha"], "tree": changes})
    if st not in (200, 201):
        raise SystemExit("建 tree 失败: %s %s" % (st, t))
    if t["sha"] != tree:                    # 这是「等价于 git push」的铁证
        raise SystemExit("tree 不一致: 远端 %s 本地 %s" % (t["sha"], tree))
    print("tree 一致 %s" % tree[:8])

    msg = git("log", "-1", "--pretty=%B").stdout.decode("utf-8").rstrip("\n")
    meta = {}
    for key, fmt in (("an", "%an"), ("ae", "%ae"), ("cn", "%cn"), ("ce", "%ce"),
                     ("ad", "%aI"), ("cd", "%cI")):
        meta[key] = git("log", "-1", "--pretty=" + fmt).stdout.decode("utf-8").strip()

    st, nc = call("POST", API + "/git/commits", {
        "message": msg, "tree": tree, "parents": [base],
        "author": {"name": meta["an"], "email": meta["ae"], "date": meta["ad"]},
        "committer": {"name": meta["cn"], "email": meta["ce"], "date": meta["cd"]},
    })
    if st not in (200, 201):
        raise SystemExit("建 commit 失败: %s %s" % (st, nc))
    print("远端 commit %s" % nc["sha"][:8])

    st, r = call("PATCH", API + "/git/refs/heads/" + BRANCH,
                 {"sha": nc["sha"], "force": False})
    if st not in (200, 201):
        raise SystemExit("更新 ref 失败: %s %s" % (st, r))
    print("推送完成")
    align(nc["sha"])
    print("git status 应该没有 ahead/behind 了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
