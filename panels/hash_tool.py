# -*- coding: utf-8 -*-
"""哈希计算工具。"""
import hashlib

import customtkinter as ctk
from tkinter import filedialog, messagebox


class HashToolPanel(ctk.CTkFrame):
    title = "哈希计算"

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="哈希计算", font=ctk.CTkFont(size=22, weight="bold"), anchor="w").pack(
            fill="x", padx=8, pady=(8, 8)
        )
        self._input = ctk.CTkTextbox(self, height=160, font=ctk.CTkFont(family="Consolas", size=13))
        self._input.pack(fill="x", padx=8, pady=(0, 8))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(row, text="计算文本", width=100, command=self._hash_text).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="计算文件", width=100, command=self._hash_file).pack(side="left")

        self._out = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13))
        self._out.pack(fill="both", expand=True, padx=8, pady=(8, 8))

    def _digest(self, data: bytes):
        return {
            "MD5": hashlib.md5(data).hexdigest(),
            "SHA1": hashlib.sha1(data).hexdigest(),
            "SHA256": hashlib.sha256(data).hexdigest(),
            "SHA512": hashlib.sha512(data).hexdigest(),
        }

    def _show(self, mapping):
        lines = [f"{k}: {v}" for k, v in mapping.items()]
        self._out.delete("1.0", "end")
        self._out.insert("1.0", "\n".join(lines))
        self.app.set_status("哈希已计算")

    def _hash_text(self):
        text = self._input.get("1.0", "end-1c")
        self._show(self._digest(text.encode("utf-8")))

    def _hash_file(self):
        path = filedialog.askopenfilename(title="选择文件")
        if not path:
            return
        try:
            h_md5 = hashlib.md5()
            h_sha1 = hashlib.sha1()
            h_sha256 = hashlib.sha256()
            h_sha512 = hashlib.sha512()
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    h_md5.update(chunk)
                    h_sha1.update(chunk)
                    h_sha256.update(chunk)
                    h_sha512.update(chunk)
            self._show(
                {
                    "文件": path,
                    "MD5": h_md5.hexdigest(),
                    "SHA1": h_sha1.hexdigest(),
                    "SHA256": h_sha256.hexdigest(),
                    "SHA512": h_sha512.hexdigest(),
                }
            )
        except Exception as e:
            messagebox.showerror("哈希计算", str(e))
