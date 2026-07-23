# -*- coding: utf-8 -*-
"""时间戳工具。"""
from datetime import datetime, timezone

import customtkinter as ctk
from tkinter import messagebox


class TimestampToolPanel(ctk.CTkFrame):
    title = "时间戳"

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="时间戳", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").pack(
            fill="x", padx=8, pady=(8, 8)
        )

        now_row = ctk.CTkFrame(self, fg_color="transparent")
        now_row.pack(fill="x", padx=8, pady=6)
        ctk.CTkButton(now_row, text="当前时间", width=100, command=self._now).pack(side="left", padx=(0, 8))
        self._now_label = ctk.CTkLabel(now_row, text="", font=ctk.CTkFont(family="Consolas", size=13), anchor="w")
        self._now_label.pack(side="left", fill="x", expand=True)

        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(row1, text="时间戳", width=70).pack(side="left")
        self._ts = ctk.CTkEntry(row1, placeholder_text="秒或毫秒")
        self._ts.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row1, text="转日期", width=80, command=self._ts_to_date).pack(side="left")

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(row2, text="日期", width=70).pack(side="left")
        self._date = ctk.CTkEntry(row2, placeholder_text="YYYY-MM-DD HH:MM:SS")
        self._date.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row2, text="转时间戳", width=90, command=self._date_to_ts).pack(side="left")

        self._out = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13))
        self._out.pack(fill="both", expand=True, padx=8, pady=(12, 8))
        self._now()

    def _show(self, text):
        self._out.delete("1.0", "end")
        self._out.insert("1.0", text)
        self.app.set_status("时间戳转换完成")

    def _now(self):
        now = datetime.now()
        utc = datetime.now(timezone.utc)
        sec = int(now.timestamp())
        ms = int(now.timestamp() * 1000)
        self._now_label.configure(text=f"{now.strftime('%Y-%m-%d %H:%M:%S')}  |  {sec} / {ms}")
        self._show(
            "\n".join(
                [
                    f"本地: {now.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"UTC : {utc.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"秒  : {sec}",
                    f"毫秒: {ms}",
                ]
            )
        )

    def _ts_to_date(self):
        raw = self._ts.get().strip()
        if not raw:
            return
        try:
            val = int(raw)
            if val > 10_000_000_000:
                val = val / 1000.0
            local = datetime.fromtimestamp(val)
            utc = datetime.fromtimestamp(val, tz=timezone.utc)
            self._show(
                "\n".join(
                    [
                        f"输入: {raw}",
                        f"本地: {local.strftime('%Y-%m-%d %H:%M:%S')}",
                        f"UTC : {utc.strftime('%Y-%m-%d %H:%M:%S')}",
                    ]
                )
            )
        except Exception as e:
            messagebox.showerror("时间戳", str(e))

    def _date_to_ts(self):
        raw = self._date.get().strip()
        if not raw:
            return
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
        ]
        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            messagebox.showerror("时间戳", "无法解析日期，请用 YYYY-MM-DD HH:MM:SS")
            return
        sec = int(dt.timestamp())
        self._show(f"日期: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n秒: {sec}\n毫秒: {sec * 1000}")
