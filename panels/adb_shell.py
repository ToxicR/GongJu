# -*- coding: utf-8 -*-
"""内置 ADB Shell 面板。"""
import threading

import customtkinter as ctk
from tkinter import messagebox

from adb_util import shell
from panels.base import BasePanel


class AdbShellPanel(BasePanel):
    title = "ADB Shell"

    def _build(self):
        ctk.CTkLabel(
            self,
            text="ADB Shell",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            self,
            text="每次执行一条 shell 命令（非交互式）。可用 ↑/↓ 浏览历史。",
            font=ctk.CTkFont(size=13),
            text_color="gray70",
            anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 8))

        self._out = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13))
        self._out.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 8))
        self._entry = ctk.CTkEntry(row, placeholder_text="例如: getprop ro.product.model")
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry.bind("<Return>", lambda _e: self._run())
        self._entry.bind("<Up>", self._hist_up)
        self._entry.bind("<Down>", self._hist_down)
        ctk.CTkButton(row, text="执行", width=80, command=self._run).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="清空", width=70, fg_color="gray", command=self._clear).pack(side="left")

        self._history = []
        self._hist_idx = -1

    def _clear(self):
        self._out.delete("1.0", "end")

    def _append(self, text):
        self._out.insert("end", text)
        self._out.see("end")

    def _hist_up(self, _event=None):
        if not self._history:
            return "break"
        if self._hist_idx < 0:
            self._hist_idx = len(self._history) - 1
        else:
            self._hist_idx = max(0, self._hist_idx - 1)
        self._entry.delete(0, "end")
        self._entry.insert(0, self._history[self._hist_idx])
        return "break"

    def _hist_down(self, _event=None):
        if not self._history or self._hist_idx < 0:
            return "break"
        self._hist_idx += 1
        if self._hist_idx >= len(self._history):
            self._hist_idx = -1
            self._entry.delete(0, "end")
            return "break"
        self._entry.delete(0, "end")
        self._entry.insert(0, self._history[self._hist_idx])
        return "break"

    def _run(self):
        adb = self.adb
        if not adb:
            messagebox.showerror("ADB Shell", "未找到 adb")
            return
        cmd = self._entry.get().strip()
        if not cmd:
            return
        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
        self._hist_idx = -1
        self._append(f"$ {cmd}\n")
        self.set_status(f"执行: {cmd}")

        def work():
            code, out, err = shell(adb, cmd, serial=self.serial, timeout=60)
            parts = []
            if out:
                parts.append(out if out.endswith("\n") else out + "\n")
            if err:
                parts.append(err if err.endswith("\n") else err + "\n")
            if not parts:
                parts.append(f"(exit {code})\n")
            text = "".join(parts) + "\n"
            self.after(0, lambda: self._finish(text, code))

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, text, code):
        self._append(text)
        self.set_status(f"完成 (exit {code})")
