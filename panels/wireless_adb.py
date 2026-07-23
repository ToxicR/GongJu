# -*- coding: utf-8 -*-
"""无线 ADB 面板。"""
import threading

import customtkinter as ctk
from tkinter import messagebox

from adb_util import list_devices_raw, run_adb
from panels.base import BasePanel


class WirelessAdbPanel(BasePanel):
    title = "无线 ADB"

    def _build(self):
        ctk.CTkLabel(
            self,
            text="无线 ADB",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            self,
            text="先用 USB 连上设备开启 tcpip，再通过 IP 连接；Android 11+ 可用无线配对。",
            font=ctk.CTkFont(size=13),
            text_color="gray70",
            anchor="w",
            wraplength=720,
        ).pack(fill="x", padx=8, pady=(0, 12))

        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(row1, text="TCP 端口", width=80).pack(side="left")
        self._tcpip_port = ctk.CTkEntry(row1, width=100)
        self._tcpip_port.insert(0, "5555")
        self._tcpip_port.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row1, text="开启 tcpip（需 USB）", width=160, command=self._tcpip).pack(side="left")

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(row2, text="连接地址", width=80).pack(side="left")
        self._connect_host = ctk.CTkEntry(row2, width=220, placeholder_text="192.168.1.8:5555")
        self._connect_host.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row2, text="连接", width=80, command=self._connect).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row2, text="断开", width=80, fg_color="gray", command=self._disconnect).pack(side="left")

        row3 = ctk.CTkFrame(self, fg_color="transparent")
        row3.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(row3, text="配对地址", width=80).pack(side="left")
        self._pair_host = ctk.CTkEntry(row3, width=180, placeholder_text="192.168.1.8:37123")
        self._pair_host.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(row3, text="配对码", width=50).pack(side="left")
        self._pair_code = ctk.CTkEntry(row3, width=100)
        self._pair_code.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row3, text="配对", width=80, command=self._pair).pack(side="left")

        ctk.CTkButton(self, text="刷新设备列表", width=120, command=self._refresh_list).pack(
            anchor="w", padx=8, pady=(12, 6)
        )
        self._box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13), height=220)
        self._box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def on_show(self):
        self._refresh_list()

    def _require_adb(self):
        adb = self.adb
        if not adb:
            messagebox.showerror("无线 ADB", "未找到 adb")
            return None
        return adb

    def _tcpip(self):
        adb = self._require_adb()
        if not adb:
            return
        port = self._tcpip_port.get().strip() or "5555"
        serial = self.serial

        def work():
            code, out, err = run_adb(adb, ["tcpip", port], serial=serial, timeout=15)
            msg = (out or err or "").strip() or ("成功" if code == 0 else "失败")
            self.after(0, lambda: self._done(f"tcpip {port}: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _connect(self):
        adb = self._require_adb()
        if not adb:
            return
        host = self._connect_host.get().strip()
        if not host:
            messagebox.showwarning("无线 ADB", "请填写连接地址，例如 192.168.1.8:5555")
            return

        def work():
            code, out, err = run_adb(adb, ["connect", host], timeout=15)
            msg = (out or err or "").strip()
            self.after(0, lambda: self._done(f"connect {host}: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _disconnect(self):
        adb = self._require_adb()
        if not adb:
            return
        host = self._connect_host.get().strip()

        def work():
            args = ["disconnect", host] if host else ["disconnect"]
            code, out, err = run_adb(adb, args, timeout=15)
            msg = (out or err or "").strip()
            self.after(0, lambda: self._done(f"disconnect: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _pair(self):
        adb = self._require_adb()
        if not adb:
            return
        host = self._pair_host.get().strip()
        code_txt = self._pair_code.get().strip()
        if not host or not code_txt:
            messagebox.showwarning("无线 ADB", "请填写配对地址和配对码")
            return

        def work():
            code, out, err = run_adb(adb, ["pair", host, code_txt], timeout=30)
            msg = (out or err or "").strip()
            self.after(0, lambda: self._done(f"pair {host}: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _refresh_list(self):
        adb = self.adb
        if not adb:
            self._box.delete("1.0", "end")
            self._box.insert("1.0", "未找到 adb")
            return
        items = list_devices_raw(adb)
        lines = ["当前设备：", ""]
        if not items:
            lines.append("(无)")
        else:
            for s, st in items:
                lines.append(f"{s}\t{st}")
        self._box.delete("1.0", "end")
        self._box.insert("1.0", "\n".join(lines))
        self.app.refresh_devices()

    def _done(self, msg):
        self.set_status(msg)
        self._refresh_list()
