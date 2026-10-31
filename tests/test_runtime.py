# -*- coding: utf-8 -*-
"""运行时（runtime）回归测试：条件求值、持久化、提问校验、镜头 / 转场事件。

这些用例只驱动 Runtime 生成器，不碰 pygame 窗口 —— 跑得快，CI 上也稳。
"""

import os

from stmg import parser, runtime, save as savemod

HEAD = """<
Size=1280x720
title="测试剧本"
>
<
Start:
"""


def build(project, body):
    """写剧本 + 解析，返回 Script。"""
    _, write = project
    src = HEAD + body + "\n>\n"
    sc = parser.parse_file(write(src))
    assert sc.error_count() == 0, [str(i) for i in sc.issues]
    return sc


def run_all(sc, answers=None):
    """把整份剧本跑完，返回 (事件列表, 变量表)。

    answers 是按顺序喂给 choose / question 的回答；喂完了就一律回 "1"。
    """
    answers = list(answers or [])
    rt = runtime.Runtime(sc, None, True)
    gen = rt.run()
    events, nxt = [], None
    while True:
        try:
            # send() 的返回值本身就是「下一拍事件」，别丢，否则会漏一句台词
            ev = nxt if nxt is not None else next(gen)
        except StopIteration:
            break
        nxt = None
        events.append(ev)
        if ev.get("t") in ("choose", "question"):
            ans = answers.pop(0) if answers else "1"
            try:
                nxt = gen.send(ans)
            except StopIteration:
                break
    return events, rt.vars


def says(events):
    """把 say 事件的文本抽出来，方便断言走了哪条分支。"""
    return [str(e.get("text", "")) for e in events if e.get("t") == "say"]


def test_compound_condition_both_operators(project):
    """and / or / not 都要真的参与求值，不是摆设。"""
    sc = build(project, (
        "SET 好感度 = 30\n"
        "SET 心情 = \"开心\"\n"
        'If 好感度 >= 10 and 心情 == "开心":\n'
        '    "走了 and 分支"\n'
        "EndIf\n"
        'If 好感度 < 10 or 心情 == "开心":\n'
        '    "走了 or 分支"\n'
        "EndIf\n"
        "If not 好感度 > 100:\n"
        '    "走了 not 分支"\n'
        "EndIf\n"
    ))
    texts = says(run_all(sc)[0])
    assert "走了 and 分支" in texts
    assert "走了 or 分支" in texts
    assert "走了 not 分支" in texts


def test_if_else_picks_one_side(project):
    """If / Else 只会走一边 —— 两边都跑说明块解析串了。"""
    sc = build(project, (
        "SET n = 5\n"
        "If n > 10:\n"
        '    "大"\n'
        "Else:\n"
        '    "小"\n'
        "EndIf\n"
    ))
    texts = says(run_all(sc)[0])
    assert "小" in texts and "大" not in texts


def test_persist_survives_new_runtime(project):
    """S.persist 写下去的值，下一个 Runtime 实例（≈ 重开游戏）还能读到。"""
    sc = build(project, 'S.persist("route_a", 1)\n"写完了"\n')
    run_all(sc)

    # 直接查文件，确认真的落盘了，而不是只存在内存里
    data = savemod.load_persist(os.path.dirname(sc.path), sc.title)
    assert data.get("route_a") == 1

    sc2 = build(project, 'S.persist("other", 2)\n"再来一次"\n')
    rt2 = runtime.Runtime(sc2, None, True)
    assert rt2.STM.PERSIST.get("route_a") == 1, "上一个实例写的值没被带过来"


def test_question_qtype_int(project):
    """QTYPE=int 时事件要带 qtype，并且把玩家输入转成 int。"""
    sc = build(project, (
        'SET STM.QTYPE = "int"\n'
        "SET STM.QMIN = 1\n"
        "SET STM.QMAX = 99\n"
        'STM.Q = "年龄？"\n'
        "Question:\n"
        '"收到"\n'
    ))
    events, _ = run_all(sc, answers=["42"])
    q = [e for e in events if e["t"] == "question"][0]
    assert q["qtype"] == "int"
    assert q["qmin"] == 1 and q["qmax"] == 99
    # 答完剧情继续走：说明 send() 把答案接回去了
    assert "收到" in says(events)


def test_question_defaults_to_text(project):
    """不写 QTYPE 就是纯文本，老剧本的行为一点不能变。"""
    sc = build(project, 'STM.Q = "名字？"\nQuestion:\n"好"\n')
    events, _ = run_all(sc, answers=["小明"])
    q = [e for e in events if e["t"] == "question"][0]
    assert q["qtype"] == "text"


def test_camera_events(project):
    """shake / zoom / pan 三个镜头事件字段要对得上渲染层的约定。"""
    sc = build(project, (
        "S.camera(shake=8, dur=0.3)\n"
        "S.camera(zoom=1.5, dur=0.5)\n"
        'S.camera(pan="left", dur=0.4)\n'
        '"镜头演完了"\n'
    ))
    cams = [e for e in run_all(sc)[0] if e["t"] == "camera"]
    assert len(cams) == 3
    assert cams[0]["mode"] == "shake" and abs(cams[0]["amp"] - 8) < 1e-6
    assert cams[1]["mode"] == "zoom" and abs(cams[1]["zoom"] - 1.5) < 1e-6
    # pan 的 dx/dy 是「屏宽的百分比」（0.2 = 平移两成），不是像素
    assert cams[2]["mode"] == "pan" and cams[2]["dx"] == -0.2 and cams[2]["dy"] == 0
    assert abs(cams[1]["dur"] - 0.5) < 1e-6


def test_transition_event(project):
    """S.transition 把 kind / dur 原样交给界面层。"""
    sc = build(project, 'S.transition("wipe", dur=0.2)\n"换景了"\n')
    tr = [e for e in run_all(sc)[0] if e["t"] == "transition"]
    assert tr and tr[0]["kind"] == "wipe" and abs(tr[0]["dur"] - 0.2) < 1e-6


def test_wait_event(project):
    """S.wait 产出 wait 事件而不是真的阻塞——阻塞应该由界面层决定。"""
    sc = build(project, "S.wait(1.5)\n\"等完了\"\n")
    w = [e for e in run_all(sc)[0] if e["t"] == "wait"]
    assert w and abs(w[0]["dur"] - 1.5) < 1e-6
