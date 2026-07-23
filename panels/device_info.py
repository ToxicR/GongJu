# -*- coding: utf-8 -*-
"""设备信息面板。"""
import threading

import customtkinter as ctk

from adb_util import run_adb, shell
from panels.base import BasePanel

_PROPS = [
    ("型号", "ro.product.model"),
    ("品牌", "ro.product.brand"),
    ("设备", "ro.product.device"),
    ("制造商", "ro.product.manufacturer"),
    ("Android 版本", "ro.build.version.release"),
    ("SDK", "ro.build.version.sdk"),
    ("构建号", "ro.build.display.id"),
    ("CPU ABI", "ro.product.cpu.abi"),
]


class DeviceInfoPanel(BasePanel):
    title = "设备信息"

    def _build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(8, 8))
        ctk.CTkLabel(
            head,
            text="设备信息",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(head, text="刷新", width=80, command=self.refresh).pack(side="right")

        self._box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13))
        self._box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def on_show(self):
        self.refresh()

    def refresh(self):
        adb = self.adb
        if not adb:
            self._box.delete("1.0", "end")
            self._box.insert("1.0", "未找到 adb，请先安装 ADB 环境。")
            return
        self.set_status("正在读取设备信息…")
        serial = self.serial

        def work():
            lines = []
            serials_note = serial or "(默认设备)"
            lines.append(f"序列号: {serials_note}")
            code, out, err = run_adb(adb, ["get-state"], serial=serial, timeout=8)
            lines.append(f"状态: {(out or err or '').strip() or ('ok' if code == 0 else '未知')}")
            for label, prop in _PROPS:
                c, o, e = shell(adb, ["getprop", prop], serial=serial, timeout=8)
                val = (o or "").strip() or (e or "").strip() or "-"
                lines.append(f"{label}: {val}")
            c, o, e = shell(adb, ["wm", "size"], serial=serial, timeout=8)
            lines.append(f"分辨率: {(o or e or '').strip() or '-'}")
            c, o, e = shell(adb, ["wm", "density"], serial=serial, timeout=8)
            lines.append(f"密度: {(o or e or '').strip() or '-'}")
            c, o, e = shell(adb, ["dumpsys", "battery"], serial=serial, timeout=12)
            level = "-"
            for line in (o or "").splitlines():
                if "level:" in line.lower():
                    level = line.split(":", 1)[-1].strip()
                    break
            lines.append(f"电量: {level}")
            text = "\n".join(lines)
            self.after(0, lambda: self._show(text))

        threading.Thread(target=work, daemon=True).start()

    def _show(self, text):
        self._box.delete("1.0", "end")
        self._box.insert("1.0", text)
        self.set_status("设备信息已更新")
