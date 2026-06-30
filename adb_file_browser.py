# -*- coding: utf-8 -*-
"""
ADB 文件浏览器
通过 adb shell ls 浏览已连接 Android 设备的目录，支持路径栏手动输入并跳转。
"""
import subprocess
import sys
import os
import re
import threading

import customtkinter as ctk
from tkinter import messagebox, filedialog

from log_viewer import find_adb, check_android_device

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _is_ls_error(text):
    if not text or not text.strip():
        return True
    t = text.strip().lower()
    if "ls:" in t or "unknown option" in t or "aborting" in t or "invalid" in t:
        return True
    if "no devices" in t or "devices/emulators" in t or "not found" in t:
        return True
    if "no such" in t or "or directory" in t or "such file" in t:
        return True
    return False


def _run_adb_ls(adb_cmd, path):
    """执行 adb shell ls <path>，返回 (stdout+stderr 合并, returncode)。"""
    path = path.rstrip("/") or "/"
    try:
        r = subprocess.run(
            [adb_cmd, "shell", "ls", path],
            capture_output=True,
            text=True,
            timeout=25,
            encoding="utf-8",
            errors="replace",
            creationflags=_CREATIONFLAGS,
        )
        out = (r.stdout or "").strip().replace("\r", "\n")
        err = (r.stderr or "").strip()
        return (out + "\n" + err).strip(), r.returncode
    except Exception:
        return "", -1


def _run_adb_cd_ls(adb_cmd, path):
    """执行 adb shell "cd <path> && ls"，用于 path 为 /sdcard 时避免 ls 只回显路径。"""
    path = path.rstrip("/") or "/"
    try:
        cmd = "cd " + path.replace("'", "'\\''") + " && ls"
        r = subprocess.run(
            [adb_cmd, "shell", cmd],
            capture_output=True,
            text=True,
            timeout=25,
            encoding="utf-8",
            errors="replace",
            creationflags=_CREATIONFLAGS,
        )
        out = (r.stdout or "").strip().replace("\r", "\n")
        err = (r.stderr or "").strip()
        return (out + "\n" + err).strip(), r.returncode
    except Exception:
        return "", -1


# 解析时忽略的 token（常见于 ls 报错或说明文字，不能当目录名）
_PARSE_SKIP_TOKENS = frozenset(
    {"no", "such", "or", "directory", "file", "and", "the", "a", "an", "in", "to", "for"}
)


def _parse_ls(combined, path_filter=""):
    """解析 ls 输出为 [(name, is_dir), ...]。过滤路径回显、报错及常见英文说明词。"""
    path_filter = (path_filter or "").rstrip("/")
    items = []
    for line in combined.splitlines():
        line = line.strip()
        if not line or _is_ls_error(line):
            continue
        if path_filter and (line == path_filter or line.rstrip("/") == path_filter):
            continue
        for part in re.split(r"[ \t;]+", line):
            part = part.strip().rstrip(";")
            if not part or _is_ls_error(part) or part in (".", ".."):
                continue
            if part.lower() in _PARSE_SKIP_TOKENS:
                continue
            if path_filter and part.rstrip("/") == path_filter:
                continue
            if part.startswith("/") and len(part) > 2:
                continue
            items.append((part, True))
    return items


def list_dir(adb_cmd, path):
    """
    列出 path 下的文件和文件夹。仅使用 adb shell ls。
    当 path 为 /sdcard 时，部分设备 ls /sdcard 只回显路径不列内容，故优先用 /storage/emulated/0 列出。
    返回 ([(name, is_dir), ...], None) 或 (None, error_msg)。
    """
    path = path.rstrip("/") or "/"

    # 当路径为 /sdcard 时：部分设备 ls /sdcard 只回显路径，ls /storage/emulated/0 可能报错，改用 cd /sdcard && ls
    if path == "/sdcard":
        combined_cd, code_cd = _run_adb_cd_ls(adb_cmd, "/sdcard")
        if combined_cd and not _is_ls_error(combined_cd):
            items = _parse_ls(combined_cd, "")
            if items:
                return items, None
        combined_alt, code_alt = _run_adb_ls(adb_cmd, "/storage/emulated/0")
        if combined_alt and not _is_ls_error(combined_alt):
            items = _parse_ls(combined_alt, "/storage/emulated/0")
            if items:
                return items, None
        combined, code = _run_adb_ls(adb_cmd, path)
        if combined and not _is_ls_error(combined):
            items = _parse_ls(combined, path)
            if items:
                return items, None
        if code_cd != 0 and combined_cd:
            return None, combined_cd.strip()
        if code_alt != 0 and combined_alt:
            return None, combined_alt.strip()
        if code != 0 and combined:
            return None, combined.strip()
        return None, "无法列出 /sdcard"

    # /sdcard/xxx：先试当前路径，无结果再试 /storage/emulated/0/xxx
    if path.startswith("/sdcard/"):
        suffix = path[7:]  # 去掉 "/sdcard"
        alt = "/storage/emulated/0/" + suffix.lstrip("/")
        combined_alt, code_alt = _run_adb_ls(adb_cmd, alt)
        if combined_alt and not _is_ls_error(combined_alt):
            items = _parse_ls(combined_alt, alt)
            if items:
                return items, None

    combined, code = _run_adb_ls(adb_cmd, path)
    if combined and not _is_ls_error(combined):
        items = _parse_ls(combined, path)
        if items:
            return items, None
    if code != 0 and combined:
        return None, combined.strip()

    if path.startswith("/sdcard/"):
        suffix = path[7:].lstrip("/")
        alt = "/storage/emulated/0/" + suffix
        combined2, code2 = _run_adb_ls(adb_cmd, alt)
        if combined2 and not _is_ls_error(combined2):
            items = _parse_ls(combined2, alt)
            if items:
                return items, None
        if code2 != 0 and combined2:
            return None, combined2.strip()

    return None, "无法列出该目录（请检查路径或权限）"


class AdbFileBrowserWindow(ctk.CTkToplevel):
    """ADB 文件浏览器窗口"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("ADB 文件浏览器")
        self.geometry("720x520")
        self.resizable(True, True)
        _icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.isfile(_icon):
            try:
                self.iconbitmap(_icon)
            except Exception:
                pass
        self._adb_cmd = None
        self._current_path = "/"
        self._loading = False

        self._build_ui()
        self._init_connection()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(top, text="路径：", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 6))
        self._path_entry = ctk.CTkEntry(
            top,
            height=28,
            font=ctk.CTkFont(size=13),
            placeholder_text="/ 或 /sdcard 或 /storage/emulated/0",
        )
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._path_entry.insert(0, "/")
        self._path_entry.bind("<Return>", lambda e: self._go_to_path())

        ctk.CTkButton(top, text="转到", width=50, command=self._go_to_path).pack(side="left", padx=(0, 8))
        ctk.CTkButton(top, text="上级", width=50, command=self._go_parent).pack(side="left", padx=(0, 4))
        ctk.CTkButton(top, text="刷新", width=50, command=self._refresh).pack(side="left")

        self._status_label = ctk.CTkLabel(
            self, text="状态：就绪", font=ctk.CTkFont(size=12), text_color="gray", anchor="w"
        )
        self._status_label.pack(fill="x", padx=12, pady=(8, 4))

        self._list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _set_status(self, msg):
        self._status_label.configure(text=f"状态：{msg}")

    def _sync_path_entry(self, path):
        path = path.rstrip("/") or "/"
        self._current_path = path
        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, path)

    def _init_connection(self):
        self._adb_cmd = find_adb()
        if not self._adb_cmd:
            self._set_status("未找到 ADB")
            messagebox.showerror("错误", "未找到 ADB，请安装 Android SDK Platform-Tools。", parent=self)
            return
        ok, _ = check_android_device(self._adb_cmd)
        if not ok:
            self._set_status("未检测到设备")
            messagebox.showwarning("未检测到设备", "请连接 Android 设备并开启 USB 调试。", parent=self)
            return
        self._set_status("已连接设备，正在加载根目录…")
        self._load_dir("/")

    def _go_to_path(self):
        path = (self._path_entry.get() or "").strip().rstrip("/") or "/"
        if not path.startswith("/"):
            path = "/" + path
        self._load_dir(path)

    def _load_dir(self, path):
        if self._loading:
            return
        self._loading = True
        path = path.rstrip("/") or "/"
        self._set_status("加载中…")
        for w in self._list_frame.winfo_children():
            w.destroy()

        def do():
            items, err = list_dir(self._adb_cmd, path)
            self.after(0, lambda p=path, i=items, e=err: self._on_done(p, i, e))

        threading.Thread(target=do, daemon=True).start()

    def _on_done(self, path, items, err):
        self._loading = False
        if err is not None or items is None:
            self._set_status(err or "未知错误")
            if err:
                messagebox.showerror("列出目录失败", err, parent=self)
            return
        self._sync_path_entry(path)
        self._set_status(f"共 {len(items)} 项")

        for name, is_dir in sorted(items, key=lambda x: (not x[1], x[0].lower())):
            row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            prefix = "[目录] " if is_dir else "[文件] "
            btn = ctk.CTkButton(
                row,
                text=prefix + name,
                anchor="w",
                fg_color="transparent" if is_dir else ("gray", "gray"),
                hover_color=("gray75", "gray25") if is_dir else ("gray60", "gray40"),
                command=lambda n=name, d=is_dir: self._on_click(n, d),
            )
            btn.pack(side="left", fill="x", expand=True)
            ctk.CTkButton(
                row,
                text="导出",
                width=50,
                command=lambda n=name: self._export_item(n),
            ).pack(side="right", padx=(4, 0))

        self._list_frame.update_idletasks()
        self._scroll_list_to_top()

    def _scroll_list_to_top(self):
        """将目录列表滚动到最顶部"""
        self._list_frame.update_idletasks()
        try:
            canvas = getattr(self._list_frame, "_parent_canvas", None)
            if canvas is None:
                for w in self._list_frame.winfo_children():
                    if w.winfo_class() == "Canvas" or hasattr(w, "yview_moveto"):
                        canvas = w
                        break
            if canvas is not None and hasattr(canvas, "yview_moveto"):
                canvas.yview_moveto(0)
        except Exception:
            pass

    def _export_item(self, name):
        """将选中的文件或文件夹从设备导出（adb pull）到本地目录"""
        device_path = (self._current_path.rstrip("/") + "/" + name).replace("//", "/")
        dest = filedialog.askdirectory(title="选择导出到的本地文件夹", parent=self)
        if not dest:
            return
        self._set_status("导出中…")

        def do_pull():
            try:
                r = subprocess.run(
                    [self._adb_cmd, "pull", device_path, dest],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=_CREATIONFLAGS,
                )
                out = (r.stdout or "").strip() + "\n" + (r.stderr or "").strip()
                self.after(0, lambda: self._on_export_done(r.returncode == 0, out, dest))
            except subprocess.TimeoutExpired:
                self.after(0, lambda: self._on_export_done(False, "导出超时", dest))
            except Exception as e:
                self.after(0, lambda: self._on_export_done(False, str(e), dest))

        threading.Thread(target=do_pull, daemon=True).start()

    def _on_export_done(self, ok, msg, dest):
        if ok:
            self._set_status("导出完成")
            messagebox.showinfo("导出完成", f"已导出到：\n{dest}", parent=self)
        else:
            self._set_status("导出失败")
            messagebox.showerror("导出失败", msg or "未知错误", parent=self)

    def _on_click(self, name, is_dir):
        if not is_dir:
            messagebox.showinfo("提示", "当前仅支持进入目录。", parent=self)
            return
        new_path = (self._current_path.rstrip("/") + "/" + name).replace("//", "/")
        self._load_dir(new_path)

    def _go_parent(self):
        if self._current_path == "/":
            return
        parent = os.path.dirname(self._current_path.rstrip("/")) or "/"
        self._load_dir(parent)

    def _refresh(self):
        self._load_dir(self._current_path)
