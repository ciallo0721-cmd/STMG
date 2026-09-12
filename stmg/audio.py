# -*- coding: utf-8 -*-
"""三通道音频：BGM（可循环）/ SE（可叠加）/ Voice（独占，新的打断旧的）。

pygame.mixer 起不来（比如没声卡）时自动降级成静音，不让游戏崩。
"""

import pygame

from . import pack


class Audio(object):
    def __init__(self):
        self.ok = False
        self.cur_bgm = ""
        self.volumes = {"bgm": 0.7, "se": 0.8, "voice": 1.0}
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)
            self.voice_channel = pygame.mixer.Channel(0)
            self.ok = True
        except pygame.error:
            self.ok = False

    # ------------------------------------------------------------------ #
    def set_volume(self, kind, value):
        if kind in self.volumes:
            self.volumes[kind] = max(0.0, min(1.0, float(value)))
        if not self.ok:
            return
        if kind == "bgm":
            pygame.mixer.music.set_volume(self.volumes["bgm"])

    def play_bgm(self, path, loop=True):
        if not self.ok or not path:
            if not path and self.ok:
                self.stop_bgm()
            return False
        if not pack.exists(path):
            return False
        if path == self.cur_bgm and pygame.mixer.music.get_busy():
            return True
        try:
            pygame.mixer.music.load(pack.open_binary(path))
            pygame.mixer.music.set_volume(self.volumes["bgm"])
            pygame.mixer.music.play(-1 if loop else 0)
            self.cur_bgm = path
            return True
        except (pygame.error, OSError):
            return False

    def stop_bgm(self):
        if self.ok:
            pygame.mixer.music.stop()
        self.cur_bgm = ""

    def _play_sound(self, path, volume):
        if not self.ok or not path or not pack.exists(path):
            return False
        try:
            snd = pygame.mixer.Sound(pack.open_binary(path))
            snd.set_volume(volume)
            snd.play()
            return True
        except (pygame.error, OSError):
            return False

    def play_se(self, path):
        return self._play_sound(path, self.volumes["se"])

    def play_voice(self, path):
        if not self.ok or not path or not pack.exists(path):
            return False
        try:
            snd = pygame.mixer.Sound(pack.open_binary(path))
            snd.set_volume(self.volumes["voice"])
            self.voice_channel.stop()
            self.voice_channel.play(snd)
            return True
        except (pygame.error, OSError):
            return False

    def apply(self, event):
        """把 Session 产生的音频事件跑一遍。"""
        t = event.get("t")
        if t == "bgm":
            self.play_bgm(event.get("path", ""), event.get("loop", True))
        elif t == "se":
            self.play_se(event.get("path", ""))
        elif t == "voice":
            self.play_voice(event.get("path", ""))
        elif t == "stop":
            what = event.get("what", "bgm")
            if what in ("bgm", "all"):
                self.stop_bgm()
            if what in ("voice", "all") and self.ok:
                self.voice_channel.stop()

    def shutdown(self):
        if self.ok:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except pygame.error:
                pass
