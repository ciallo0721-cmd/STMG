# -*- coding: utf-8 -*-
"""三通道音频：BGM（可循环）/ SE（可叠加）/ Voice（独占，新的打断旧的）。

pygame.mixer 起不来（比如没声卡）时自动降级成静音，不让游戏崩。

第 2 期（T5）新增能力：
- 每帧 `update(dt)` 驱动 BGM / 语音的淡入淡出（基于时间插值，不阻塞主循环）；
- `play_bgm(path, loop, fade)` 支持淡入；
- `fade_out(kind, dur)` 支持淡出（到点自动停）；
- `set_bgm_list(paths)` 顺序播放列表；
- `replay_voice()` 重听最后一句语音；
- `supported_exts()` 返回本环境支持的扩展名集合（flac 视 SDL_mixer 而定，统一尝试加载，
  失败再提示，不写死）。
"""

import os
import sys

import pygame

from . import pack


class Audio(object):
    def __init__(self):
        self.ok = False
        self.cur_bgm = ""
        self.volumes = {"bgm": 0.7, "se": 0.8, "voice": 1.0}
        # 实际正在施加给混音器的音量（淡入淡出过程中会和 volumes 不同）
        self._actual = {"bgm": 0.0, "voice": 1.0}
        # 进行中的淡变：kind -> {"from","to","t","dur","stop"}
        self._fades = {}
        # 播放列表（顺序播放）
        self._playlist = []
        self._playlist_loop = True
        self._list_active = False
        self._list_fade = 0.0
        # 最后一句语音的路径（供「重听」）
        self.last_voice = ""
        # 给上层（gui）消费的一次性提示（比如 flac 放不出来）
        self.toasts = []
        self._toast_cb = None
        # dev 模式：默认看环境变量，gui 也可以显式 set_dev_mode
        self.dev_mode = os.environ.get("STMG_DEV") == "1"
        self._flac_warned = False
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)
            self.voice_channel = pygame.mixer.Channel(0)
            # 打字机音效专用通道，避免打断正在播放的 BGM / SE 通道
            self.type_channel = pygame.mixer.Channel(15)
            self.ok = True
        except pygame.error:
            self.ok = False

    # ------------------------------------------------------------------ #
    # 给 gui 接线用的小钩子（不强制；没接也不影响运行）
    def set_dev_mode(self, flag):
        self.dev_mode = bool(flag)

    def set_toast(self, cb):
        """注册一个提示回调（如 gui 想把 toasts 显示成右上角提示）。"""
        self._toast_cb = cb

    def drain_toasts(self):
        """取出并清空待提示列表（gui 每帧来取一次即可）。"""
        if not self.toasts:
            return []
        out = list(self.toasts)
        self.toasts = []
        return out

    # ------------------------------------------------------------------ #
    def set_volume(self, kind, value):
        if kind in self.volumes:
            self.volumes[kind] = max(0.0, min(1.0, float(value)))
        if not self.ok:
            return
        if kind == "bgm":
            # 如果正在淡入淡出，把目标值一起改了，结尾自然落到新音量
            f = self._fades.get("bgm")
            if f and not f.get("stop"):
                f["to"] = self.volumes["bgm"]
            pygame.mixer.music.set_volume(self.volumes["bgm"])

    def supported_exts(self):
        """本环境支持的音频扩展名。flac 不写死，统一走「尝试加载，失败再提示」。"""
        return {"mp3", "wav", "ogg", "flac"}

    # ------------------------------------------------------------------ #
    # BGM：单文件（可淡入）/ 逗号列表（幂等，多路径走播放列表）
    def play_bgm(self, path, loop=True, fade=0.0, _from_list=False):
        # 逗号路径列表：T1 可能已经拆过，也可能没拆。这里做幂等处理，
        # 拆完只剩一个就按普通播放处理。
        if path and "," in path:
            parts = [p.strip() for p in path.split(",") if p.strip()]
            if len(parts) > 1:
                self.set_bgm_list(parts, loop=loop, fade=fade)
                return True
            elif len(parts) == 1:
                path = parts[0]
            else:
                return False

        if not self.ok or not path:
            if not path and self.ok:
                self.stop_bgm()
            return False
        if not pack.exists(path):
            return False
        if path == self.cur_bgm and pygame.mixer.music.get_busy():
            return True
        # 外部直接切歌：清掉旧的播放列表，避免和顺序播放打架；
        # 来自列表内部推进的调用不要清，否则会把列表自己清掉。
        if not _from_list:
            self._playlist = []
            self._list_active = False
        try:
            pygame.mixer.music.load(pack.open_binary(path))
            pygame.mixer.music.set_volume(self.volumes["bgm"])
            pygame.mixer.music.play(-1 if loop else 0)
            self.cur_bgm = path
            target = self.volumes["bgm"]
            fade = float(fade or 0.0)
            if fade > 0:
                # 从 0 淡入到目标音量
                self._actual["bgm"] = 0.0
                pygame.mixer.music.set_volume(0.0)
                self._fades["bgm"] = {"from": 0.0, "to": target,
                                      "t": 0.0, "dur": fade, "stop": False}
            else:
                self._actual["bgm"] = target
            return True
        except (pygame.error, OSError) as e:
            self._handle_load_fail(path, e)
            return False

    def stop_bgm(self):
        if self.ok:
            pygame.mixer.music.stop()
        self.cur_bgm = ""
        self._list_active = False

    def set_bgm_list(self, paths, loop=True, fade=0.0):
        """顺序播放列表。paths 可以是 list，或用逗号分隔的字符串。"""
        if isinstance(paths, str):
            paths = [p.strip() for p in paths.split(",") if p.strip()]
        paths = [p.strip() for p in paths if p.strip()]
        self._playlist_loop = bool(loop)
        self._list_fade = float(fade or 0.0)
        if not paths:
            self._playlist = []
            self.stop_bgm()
            return
        if len(paths) == 1:
            # 幂等：只剩一个就当普通播放
            self.play_bgm(paths[0], loop=loop, fade=self._list_fade)
            self._playlist = []
            return
        self._playlist = list(paths)
        self._play_next_in_list(first=True)

    def _play_next_in_list(self, first=False):
        if not self._playlist:
            self._list_active = False
            return
        p = self._playlist.pop(0)
        self._list_active = True
        ok = self.play_bgm(p, loop=False,
                           fade=(self._list_fade if first else 0.0),
                           _from_list=True)
        if not ok:
            # 这一首缺失：跳过，接着放下一首（全部缺失时会自然排空停下）
            self._play_next_in_list(first=False)
            return
        # 循环模式：把刚放过的这首重新排到队尾
        if self._playlist_loop:
            self._playlist.append(p)

    def fade_out(self, kind="bgm", dur=0.6):
        """淡出。kind 支持 "bgm" 或 "all"（顺带把语音也淡掉）。"""
        dur = float(dur or 0.0)
        if not self.ok:
            if kind in ("bgm", "all"):
                self.stop_bgm()
            if kind in ("voice", "all"):
                self.voice_channel.stop()
            return
        kinds = ("bgm", "voice") if kind == "all" else (kind,)
        for k in kinds:
            if k == "bgm":
                if self.cur_bgm or pygame.mixer.music.get_busy():
                    self._fades["bgm"] = {
                        "from": self._actual["bgm"],
                        "to": 0.0, "t": 0.0,
                        "dur": dur, "stop": True}
            elif k == "voice":
                self._fades["voice"] = {
                    "from": self._actual["voice"],
                    "to": 0.0, "t": 0.0,
                    "dur": dur, "stop": True}

    # ------------------------------------------------------------------ #
    def _play_sound(self, path, volume):
        if not self.ok or not path or not pack.exists(path):
            return False
        try:
            snd = pygame.mixer.Sound(pack.open_binary(path))
            snd.set_volume(volume)
            snd.play()
            return True
        except (pygame.error, OSError) as e:
            self._handle_load_fail(path, e)
            return False

    def play_se(self, path):
        return self._play_sound(path, self.volumes["se"])

    def play_se_once(self, path, volume=0.5):
        """短促的一次性音效（打字机用）：走专用通道，不干扰 BGM / 普通 SE。

        path 为空或素材缺失时直接返回 False，不发声。
        """
        if not self.ok or not path or not pack.exists(path):
            return False
        try:
            snd = pygame.mixer.Sound(pack.open_binary(path))
            snd.set_volume(max(0.0, min(1.0, float(volume))))
            self.type_channel.play(snd)
            return True
        except (pygame.error, OSError) as e:
            self._handle_load_fail(path, e)
            return False

    def play_voice(self, path):
        if not self.ok or not path or not pack.exists(path):
            return False
        try:
            snd = pygame.mixer.Sound(pack.open_binary(path))
            snd.set_volume(self.volumes["voice"])
            self.voice_channel.stop()
            self.voice_channel.play(snd)
            self.last_voice = path
            return True
        except (pygame.error, OSError) as e:
            self._handle_load_fail(path, e)
            return False

    def replay_voice(self):
        """重听最后一句语音。没有可重听的语音时返回 False（不崩）。"""
        if self.last_voice and self.ok and pack.exists(self.last_voice):
            self.play_voice(self.last_voice)
            return True
        return False

    # ------------------------------------------------------------------ #
    def apply(self, event):
        """把 Session 产生的音频事件跑一遍。认识 bgm/stop 上的 fade 字段。"""
        t = event.get("t")
        if t == "bgm":
            self.play_bgm(event.get("path", ""),
                          loop=event.get("loop", True),
                          fade=float(event.get("fade", 0.0) or 0.0))
        elif t == "se":
            self.play_se(event.get("path", ""))
        elif t == "voice":
            self.play_voice(event.get("path", ""))
        elif t == "stop":
            what = event.get("what", "bgm")
            fade = float(event.get("fade", 0.0) or 0.0)
            if fade > 0:
                self.fade_out(what, fade)
            else:
                if what in ("bgm", "all"):
                    self.stop_bgm()
                if what in ("voice", "all") and self.ok:
                    self.voice_channel.stop()

    # ------------------------------------------------------------------ #
    def update(self, dt):
        """每帧调用，驱动淡入淡出与播放列表推进。基于 dt 的时间插值，绝不阻塞。"""
        if not self.ok:
            return

        # 1) 推进淡入淡出
        for kind in ("bgm", "voice"):
            f = self._fades.get(kind)
            if not f:
                continue
            f["t"] += dt
            if f["dur"] <= 0:
                r = 1.0
            else:
                r = min(1.0, f["t"] / f["dur"])
            vol = f["from"] + (f["to"] - f["from"]) * r
            self._actual[kind] = vol
            self._apply_vol(kind, vol)
            if r >= 1.0:
                stop = f.get("stop")
                del self._fades[kind]
                if stop:
                    self._stop_kind(kind)

        # 2) 播放列表推进：当前曲目放完就放下一首
        if self._list_active and "bgm" not in self._fades:
            if not pygame.mixer.music.get_busy():
                if self._playlist:
                    self._play_next_in_list()
                else:
                    self._list_active = False

    def _apply_vol(self, kind, vol):
        if kind == "bgm":
            pygame.mixer.music.set_volume(vol)
        elif kind == "voice":
            self.voice_channel.set_volume(vol)

    def _stop_kind(self, kind):
        if kind == "bgm":
            self.stop_bgm()
            self._actual["bgm"] = 0.0
        elif kind == "voice":
            if self.ok:
                self.voice_channel.stop()
            self._actual["voice"] = self.volumes["voice"]

    # ------------------------------------------------------------------ #
    def _handle_load_fail(self, path, exc):
        """加载失败的兜底：flac 这类视 SDL_mixer 版本而定的格式，尝试加载失败后
        在 dev 模式提示一次「建议转 ogg/mp3」，但绝不让游戏崩。"""
        if (isinstance(path, str) and path.lower().endswith(".flac")
                and self.dev_mode and not self._flac_warned):
            self._flac_warned = True
            msg = "这个 flac 放不出来，建议转成 ogg/mp3"
            self.toasts.append(msg)
            if self._toast_cb:
                try:
                    self._toast_cb(msg)
                except Exception:                   # noqa: BLE001
                    pass
            print("[STMG 音频] " + msg, file=sys.stderr)

    def shutdown(self):
        if self.ok:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except pygame.error:
                pass
