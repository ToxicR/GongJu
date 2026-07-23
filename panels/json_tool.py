# -*- coding: utf-8 -*-
"""JSON 格式化工具。"""
import json

import customtkinter as ctk
from tkinter import messagebox


class JsonToolPanel(ctk.CTkFrame):
    title = "JSON 格式化"

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="JSON 格式化", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").pack(
            fill="x", padx=8, pady=(8, 8)
        )
        self._input = ctk.CTkTextbox(self, height=200, font=ctk.CTkFont(family="Consolas", size=13))
        self._input.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(row, text="格式化", width=90, command=self._pretty).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="压缩", width=90, command=self._minify).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="校验", width=90, command=self._validate).pack(side="left")

        self._out = ctk.CTkTextbox(self, height=220, font=ctk.CTkFont(family="Consolas", size=13))
        self._out.pack(fill="both", expand=True, padx=8, pady=(8, 8))

    def _parse(self):
        raw = self._input.get("1.0", "end-1c").strip()
        if not raw:
            raise ValueError("输入为空")
        return json.loads(raw)

    def _set(self, text):
        self._out.delete("1.0", "end")
        self._out.insert("1.0", text)
        self.app.set_status("JSON 处理完成")

    def _pretty(self):
        try:
            data = self._parse()
            self._set(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            messagebox.showerror("JSON", str(e))

    def _minify(self):
        try:
            data = self._parse()
            self._set(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        except Exception as e:
            messagebox.showerror("JSON", str(e))

    def _validate(self):
        try:
            self._parse()
            self._set("JSON 有效")
            messagebox.showinfo("JSON", "JSON 有效")
        except Exception as e:
            messagebox.showerror("JSON", str(e))
