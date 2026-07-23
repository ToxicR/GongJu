# -*- coding: utf-8 -*-
"""端口转发面板。"""
import threading

import customtkinter as ctk
from tkinter import messagebox

from adb_util import run_adb
from panels.base import BasePanel


class PortForwardPanel(BasePanel):
    title = "端口转发"

    def _build(self):
        ctk.CTkLabel(
            self,
            text="端口转发",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            self,
            text="将本机端口转发到设备端口（adb forward tcp:本机 tcp:设备）。",
            font=ctk.CTkFont(size=13),
            text_color="gray70",
            anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 12))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(row, text="本机端口", width=70).pack(side="left")
        self._local = ctk.CTkEntry(row, width=100)
        self._local.insert(0, "8080")
        self._local.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row, text="设备端口", width=70).pack(side="left")
        self._remote = ctk.CTkEntry(row, width=100)
        self._remote.insert(0, "8080")
        self._remote.pack(side="left", padx=(0, 12))
        ctk.CTkButton(row, text="添加转发", width=100, command=self._add).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="移除", width=80, fg_color="gray", command=self._remove).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="全部移除", width=90, fg_color="#8B3A3A", command=self._remove_all).pack(side="left")

        ctk.CTkButton(self, text="刷新列表", width=100, command=self._refresh).pack(anchor="w", padx=8, pady=(12, 6))
        self._box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13))
        self._box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def on_show(self):
        self._refresh()

    def _require_adb(self):
        adb = self.adb
        if not adb:
            messagebox.showerror("端口转发", "未找到 adb")
            return None
        return adb

    def _add(self):
        adb = self._require_adb()
        if not adb:
            return
        local = self._local.get().strip()
        remote = self._remote.get().strip()
        if not local.isdigit() or not remote.isdigit():
            messagebox.showwarning("端口转发", "端口需为数字")
            return

        def work():
            code, out, err = run_adb(
                adb,
                ["forward", f"tcp:{local}", f"tcp:{remote}"],
                serial=self.serial,
                timeout=10,
            )
            msg = (out or err or "").strip() or ("成功" if code == 0 else "失败")
            self.after(0, lambda: self._done(f"forward {local}->{remote}: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _remove(self):
        adb = self._require_adb()
        if not adb:
            return
        local = self._local.get().strip()
        if not local.isdigit():
            messagebox.showwarning("端口转发", "请填写要移除的本机端口")
            return

        def work():
            code, out, err = run_adb(
                adb, ["forward", "--remove", f"tcp:{local}"], serial=self.serial, timeout=10
            )
            msg = (out or err or "").strip() or ("成功" if code == 0 else "失败")
            self.after(0, lambda: self._done(f"remove {local}: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _remove_all(self):
        adb = self._require_adb()
        if not adb:
            return

        def work():
            code, out, err = run_adb(adb, ["forward", "--remove-all"], timeout=10)
            msg = (out or err or "").strip() or ("成功" if code == 0 else "失败")
            self.after(0, lambda: self._done(f"remove-all: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _refresh(self):
        adb = self.adb
        if not adb:
            self._box.delete("1.0", "end")
            self._box.insert("1.0", "未找到 adb")
            return

        def work():
            code, out, err = run_adb(adb, ["forward", "--list"], serial=self.serial, timeout=10)
            text = (out or err or "").strip() or "(无转发)"
            self.after(0, lambda: self._show(text))

        threading.Thread(target=work, daemon=True).start()

    def _show(self, text):
        self._box.delete("1.0", "end")
        self._box.insert("1.0", text)

    def _done(self, msg):
        self.set_status(msg)
        self._refresh()
