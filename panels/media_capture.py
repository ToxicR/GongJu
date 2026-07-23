# -*- coding: utf-8 -*-
"""截图与录屏面板。"""
import os
import threading
import time
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

from adb_util import run_adb, shell
from panels.base import BasePanel


class MediaCapturePanel(BasePanel):
    title = "截图 / 录屏"

    def _build(self):
        ctk.CTkLabel(
            self,
            text="截图 / 录屏",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(
            self,
            text="截图保存为 PNG；录屏使用 adb shell screenrecord，结束后拉取到本机。",
            font=ctk.CTkFont(size=13),
            text_color="gray70",
            anchor="w",
            wraplength=720,
        ).pack(fill="x", padx=8, pady=(0, 12))

        shot_row = ctk.CTkFrame(self, fg_color="transparent")
        shot_row.pack(fill="x", padx=8, pady=6)
        ctk.CTkButton(shot_row, text="截图并保存", width=140, height=36, command=self._screenshot).pack(
            side="left"
        )

        rec_row = ctk.CTkFrame(self, fg_color="transparent")
        rec_row.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(rec_row, text="录制秒数", width=70).pack(side="left")
        self._seconds = ctk.CTkEntry(rec_row, width=80)
        self._seconds.insert(0, "10")
        self._seconds.pack(side="left", padx=(0, 12))
        self._btn_rec = ctk.CTkButton(rec_row, text="开始录屏", width=120, command=self._record)
        self._btn_rec.pack(side="left")

        self._log = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13), height=260)
        self._log.pack(fill="both", expand=True, padx=8, pady=(12, 8))
        self._recording = False

    def _append(self, msg):
        self._log.insert("end", msg + "\n")
        self._log.see("end")

    def _require_adb(self):
        adb = self.adb
        if not adb:
            messagebox.showerror("截图 / 录屏", "未找到 adb")
            return None
        return adb

    def _default_dir(self):
        return os.path.join(os.path.expanduser("~"), "Desktop")

    def _screenshot(self):
        adb = self._require_adb()
        if not adb:
            return
        default_name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = filedialog.asksaveasfilename(
            title="保存截图",
            defaultextension=".png",
            initialdir=self._default_dir(),
            initialfile=default_name,
            filetypes=[("PNG", "*.png")],
        )
        if not path:
            return
        self.set_status("正在截图…")
        self._append(f"截图 -> {path}")

        def work():
            code, out, err = run_adb(
                adb,
                ["exec-out", "screencap", "-p"],
                serial=self.serial,
                timeout=30,
                text=False,
            )
            if code != 0 or not out:
                msg = err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err)
                self.after(0, lambda: self._fail(f"截图失败: {msg or code}"))
                return
            try:
                with open(path, "wb") as f:
                    f.write(out)
            except Exception as e:
                self.after(0, lambda: self._fail(f"保存失败: {e}"))
                return
            self.after(0, lambda: self._ok(f"截图已保存: {path}"))

        threading.Thread(target=work, daemon=True).start()

    def _record(self):
        if self._recording:
            return
        adb = self._require_adb()
        if not adb:
            return
        try:
            seconds = int(self._seconds.get().strip())
        except ValueError:
            messagebox.showwarning("截图 / 录屏", "录制秒数需为整数")
            return
        seconds = max(1, min(seconds, 180))
        default_name = f"record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        path = filedialog.asksaveasfilename(
            title="保存录屏",
            defaultextension=".mp4",
            initialdir=self._default_dir(),
            initialfile=default_name,
            filetypes=[("MP4", "*.mp4")],
        )
        if not path:
            return

        remote = f"/sdcard/gongju_record_{int(time.time())}.mp4"
        self._recording = True
        self._btn_rec.configure(state="disabled", text="录制中…")
        self.set_status(f"录屏 {seconds}s…")
        self._append(f"开始录屏 {seconds}s -> {path}")

        def work():
            code, out, err = shell(
                adb,
                ["screenrecord", "--time-limit", str(seconds), remote],
                serial=self.serial,
                timeout=seconds + 30,
            )
            if code != 0:
                msg = (out or err or "").strip() or str(code)
                self.after(0, lambda: self._fail(f"录屏失败: {msg}"))
                return
            code2, out2, err2 = run_adb(
                adb, ["pull", remote, path], serial=self.serial, timeout=120
            )
            shell(adb, ["rm", remote], serial=self.serial, timeout=10)
            if code2 != 0:
                msg = (out2 or err2 or "").strip() or str(code2)
                self.after(0, lambda: self._fail(f"拉取失败: {msg}"))
                return
            self.after(0, lambda: self._ok(f"录屏已保存: {path}"))

        threading.Thread(target=work, daemon=True).start()

    def _ok(self, msg):
        self._recording = False
        self._btn_rec.configure(state="normal", text="开始录屏")
        self._append(msg)
        self.set_status(msg)

    def _fail(self, msg):
        self._recording = False
        self._btn_rec.configure(state="normal", text="开始录屏")
        self._append(msg)
        self.set_status(msg)
        messagebox.showerror("截图 / 录屏", msg)
