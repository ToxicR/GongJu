# -*- coding: utf-8 -*-
"""编码转换工具。"""
import base64
import binascii
from urllib.parse import quote, unquote

import customtkinter as ctk
from tkinter import messagebox


class EncodingToolPanel(ctk.CTkFrame):
    title = "编码转换"

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="编码转换", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").pack(
            fill="x", padx=8, pady=(8, 8)
        )
        self._input = ctk.CTkTextbox(self, height=180, font=ctk.CTkFont(family="Consolas", size=13))
        self._input.pack(fill="x", padx=8, pady=(0, 8))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        actions = [
            ("Base64 编码", self._b64_enc),
            ("Base64 解码", self._b64_dec),
            ("URL 编码", self._url_enc),
            ("URL 解码", self._url_dec),
            ("Unicode 转义", self._unicode_esc),
            ("Unicode 还原", self._unicode_unesc),
            ("Hex 编码", self._hex_enc),
            ("Hex 解码", self._hex_dec),
        ]
        for i, (label, cmd) in enumerate(actions):
            ctk.CTkButton(row, text=label, width=110, command=cmd).grid(
                row=i // 4, column=i % 4, padx=4, pady=4, sticky="w"
            )

        self._out = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13))
        self._out.pack(fill="both", expand=True, padx=8, pady=(8, 8))

    def _text(self):
        return self._input.get("1.0", "end-1c")

    def _set(self, text):
        self._out.delete("1.0", "end")
        self._out.insert("1.0", text)
        self.app.set_status("转换完成")

    def _b64_enc(self):
        self._set(base64.b64encode(self._text().encode("utf-8")).decode("ascii"))

    def _b64_dec(self):
        try:
            raw = base64.b64decode(self._text().strip(), validate=False)
            self._set(raw.decode("utf-8", errors="replace"))
        except Exception as e:
            messagebox.showerror("编码转换", str(e))

    def _url_enc(self):
        self._set(quote(self._text(), safe=""))

    def _url_dec(self):
        self._set(unquote(self._text()))

    def _unicode_esc(self):
        self._set(self._text().encode("unicode_escape").decode("ascii"))

    def _unicode_unesc(self):
        try:
            self._set(self._text().encode("utf-8").decode("unicode_escape"))
        except Exception as e:
            messagebox.showerror("编码转换", str(e))

    def _hex_enc(self):
        self._set(binascii.hexlify(self._text().encode("utf-8")).decode("ascii"))

    def _hex_dec(self):
        try:
            raw = binascii.unhexlify(self._text().strip().replace(" ", ""))
            self._set(raw.decode("utf-8", errors="replace"))
        except Exception as e:
            messagebox.showerror("编码转换", str(e))
