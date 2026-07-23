# -*- coding: utf-8 -*-
"""应用管理：安装/卸载/强停/清数据/包名列表。"""
import os
import threading

import customtkinter as ctk
from tkinter import filedialog, messagebox

from adb_util import run_adb, shell
from panels.base import BasePanel


class AppManagerPanel(BasePanel):
    title = "应用管理"

    def _build(self):
        ctk.CTkLabel(
            self,
            text="应用管理",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(8, 4))

        install_row = ctk.CTkFrame(self, fg_color="transparent")
        install_row.pack(fill="x", padx=8, pady=6)
        ctk.CTkButton(install_row, text="选择 APK 安装", width=130, command=self._install_apk).pack(side="left")
        self._replace = ctk.CTkCheckBox(install_row, text="覆盖安装 (-r)")
        self._replace.select()
        self._replace.pack(side="left", padx=12)

        pkg_row = ctk.CTkFrame(self, fg_color="transparent")
        pkg_row.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(pkg_row, text="包名", width=40).pack(side="left")
        self._pkg = ctk.CTkEntry(pkg_row, placeholder_text="com.example.app")
        self._pkg.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(pkg_row, text="卸载", width=70, command=self._uninstall).pack(side="left", padx=2)
        ctk.CTkButton(pkg_row, text="强停", width=70, command=self._force_stop).pack(side="left", padx=2)
        ctk.CTkButton(pkg_row, text="清数据", width=70, fg_color="#8B3A3A", command=self._clear_data).pack(
            side="left", padx=2
        )

        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(filter_row, text="筛选", width=40).pack(side="left")
        self._filter = ctk.CTkEntry(filter_row, placeholder_text="关键字过滤包名")
        self._filter.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._filter.bind("<KeyRelease>", lambda _e: self._apply_filter())
        self._third_only = ctk.CTkCheckBox(filter_row, text="仅第三方", command=self._reload_packages)
        self._third_only.select()
        self._third_only.pack(side="left", padx=(0, 8))
        ctk.CTkButton(filter_row, text="刷新列表", width=90, command=self._reload_packages).pack(side="left")

        self._list = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12))
        self._list.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._list.bind("<Double-Button-1>", self._pick_package)

        ctk.CTkLabel(
            self,
            text="双击列表中的包名可填入上方输入框",
            font=ctk.CTkFont(size=12),
            text_color="gray60",
            anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 8))

        self._all_packages = []

    def on_show(self):
        self._reload_packages()

    def _require_adb(self):
        adb = self.adb
        if not adb:
            messagebox.showerror("应用管理", "未找到 adb")
            return None
        return adb

    def _install_apk(self):
        adb = self._require_adb()
        if not adb:
            return
        path = filedialog.askopenfilename(
            title="选择 APK",
            filetypes=[("APK", "*.apk"), ("所有文件", "*.*")],
        )
        if not path:
            return
        args = ["install"]
        if self._replace.get():
            args.append("-r")
        args.append(path)
        self.set_status(f"正在安装 {os.path.basename(path)}…")

        def work():
            code, out, err = run_adb(adb, args, serial=self.serial, timeout=180)
            msg = (out or err or "").strip() or ("成功" if code == 0 else "失败")
            self.after(0, lambda: self._done(f"安装: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _uninstall(self):
        adb = self._require_adb()
        if not adb:
            return
        pkg = self._pkg.get().strip()
        if not pkg:
            messagebox.showwarning("应用管理", "请填写包名")
            return
        if not messagebox.askyesno("应用管理", f"确认卸载 {pkg}？"):
            return

        def work():
            code, out, err = run_adb(adb, ["uninstall", pkg], serial=self.serial, timeout=60)
            msg = (out or err or "").strip() or ("成功" if code == 0 else "失败")
            self.after(0, lambda: self._done(f"卸载 {pkg}: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _force_stop(self):
        adb = self._require_adb()
        if not adb:
            return
        pkg = self._pkg.get().strip()
        if not pkg:
            messagebox.showwarning("应用管理", "请填写包名")
            return

        def work():
            code, out, err = shell(adb, ["am", "force-stop", pkg], serial=self.serial, timeout=20)
            msg = (out or err or "").strip() or ("成功" if code == 0 else "失败")
            self.after(0, lambda: self._done(f"强停 {pkg}: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _clear_data(self):
        adb = self._require_adb()
        if not adb:
            return
        pkg = self._pkg.get().strip()
        if not pkg:
            messagebox.showwarning("应用管理", "请填写包名")
            return
        if not messagebox.askyesno("应用管理", f"确认清除 {pkg} 的全部数据？"):
            return

        def work():
            code, out, err = shell(adb, ["pm", "clear", pkg], serial=self.serial, timeout=30)
            msg = (out or err or "").strip() or ("成功" if code == 0 else "失败")
            self.after(0, lambda: self._done(f"清数据 {pkg}: {msg}"))

        threading.Thread(target=work, daemon=True).start()

    def _reload_packages(self):
        adb = self.adb
        if not adb:
            self._list.delete("1.0", "end")
            self._list.insert("1.0", "未找到 adb")
            return
        self.set_status("正在加载应用列表…")
        third = bool(self._third_only.get())

        def work():
            args = ["pm", "list", "packages"]
            if third:
                args.append("-3")
            code, out, err = shell(adb, args, serial=self.serial, timeout=60)
            pkgs = []
            for line in (out or "").splitlines():
                line = line.strip()
                if line.startswith("package:"):
                    pkgs.append(line.split(":", 1)[1].strip())
            pkgs.sort()
            self.after(0, lambda: self._set_packages(pkgs, err if code != 0 else ""))

        threading.Thread(target=work, daemon=True).start()

    def _set_packages(self, pkgs, err):
        self._all_packages = pkgs
        if err and not pkgs:
            self._list.delete("1.0", "end")
            self._list.insert("1.0", err)
            self.set_status("加载失败")
            return
        self._apply_filter()
        self.set_status(f"已加载 {len(pkgs)} 个应用")

    def _apply_filter(self):
        key = (self._filter.get() or "").strip().lower()
        items = [p for p in self._all_packages if key in p.lower()] if key else list(self._all_packages)
        self._list.delete("1.0", "end")
        self._list.insert("1.0", "\n".join(items) if items else "(无匹配)")

    def _pick_package(self, _event=None):
        try:
            index = self._list.index("insert linestart")
            line = self._list.get(index, f"{index} lineend").strip()
        except Exception:
            return
        if line and not line.startswith("("):
            self._pkg.delete(0, "end")
            self._pkg.insert(0, line)

    def _done(self, msg):
        self.set_status(msg)
        self._reload_packages()
