# -*- coding: utf-8 -*-
"""
ADB 环境自动安装与配置
从软件内置 Platform-Tools 复制到本机并加入用户 PATH。
"""
import ctypes
import os
import shutil
import subprocess
import sys
import threading

import customtkinter as ctk
from tkinter import messagebox

from adb_paths import INSTALL_DIR, INSTALLED_ADB_EXE, get_bundled_platform_tools_dir
from log_viewer import find_adb


def get_install_dir():
    return INSTALL_DIR


def _verify_adb(adb_path):
    if not adb_path or not os.path.isfile(adb_path):
        return False, "adb 可执行文件不存在"
    try:
        r = subprocess.run(
            [adb_path, "version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "adb version 执行失败").strip()
        return True, (r.stdout or "").strip().splitlines()[0] if r.stdout else "adb 可用"
    except Exception as e:
        return False, str(e)


def _is_path_in_user_path(path):
    if sys.platform != "win32":
        return False
    import winreg

    norm_target = os.path.normcase(os.path.normpath(path))
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            value, _ = winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
        return False
    except OSError:
        return False

    for item in value.split(";"):
        item = item.strip()
        if not item:
            continue
        if os.path.normcase(os.path.normpath(os.path.expandvars(item))) == norm_target:
            return True
    return False


def _add_to_user_path(path):
    if sys.platform != "win32":
        raise RuntimeError("当前仅支持在 Windows 上配置 PATH")

    import winreg

    norm_target = os.path.normcase(os.path.normpath(path))
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        ) as key:
            try:
                current, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current = ""

            entries = [p.strip() for p in current.split(";") if p.strip()]
            for item in entries:
                if os.path.normcase(os.path.normpath(os.path.expandvars(item))) == norm_target:
                    return False

            entries.append(path)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(entries))
    except OSError as e:
        raise RuntimeError(f"写入用户 PATH 失败: {e}") from e

    _broadcast_environment_change()
    return True


def _broadcast_environment_change():
    if sys.platform != "win32":
        return
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x1A
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        "Environment",
        SMTO_ABORTIFHUNG,
        5000,
        ctypes.byref(result),
    )


def _copy_bundled_platform_tools(dest_dir, progress_callback=None):
    src_dir = get_bundled_platform_tools_dir()
    adb_src = os.path.join(src_dir, "adb.exe")
    if not os.path.isdir(src_dir) or not os.path.isfile(adb_src):
        raise FileNotFoundError(f"软件内置 ADB 资料不完整，请确认存在：{src_dir}")

    os.makedirs(dest_dir, exist_ok=True)
    files = sorted(
        name for name in os.listdir(src_dir)
        if os.path.isfile(os.path.join(src_dir, name))
    )
    if not files:
        raise FileNotFoundError(f"软件内置 ADB 资料为空：{src_dir}")

    total = len(files)
    for index, name in enumerate(files, start=1):
        shutil.copy2(os.path.join(src_dir, name), os.path.join(dest_dir, name))
        if progress_callback:
            progress_callback(index / total)


def install_adb_environment(log_callback=None, progress_callback=None, force=False):
    """
    从软件内置资料安装并配置 ADB 环境。
    返回 (success: bool, message: str)
    """
    if sys.platform != "win32":
        return False, "ADB 自动安装目前仅支持 Windows 系统"

    def log(msg):
        if log_callback:
            log_callback(msg)

    existing = find_adb()
    if not force and existing and os.path.isfile(existing) and _is_path_in_user_path(os.path.dirname(existing)):
        ok, version = _verify_adb(existing)
        if ok:
            msg = f"ADB 已安装且已配置：{existing}\n{version}"
            log(msg)
            return True, msg

    need_copy = force or not os.path.isfile(INSTALLED_ADB_EXE)
    if need_copy:
        bundled_dir = get_bundled_platform_tools_dir()
        if force and os.path.isdir(INSTALL_DIR):
            log("正在使用软件内置资料更新 Platform-Tools...")
        else:
            log(f"正在从软件内置资料安装 Platform-Tools...\n来源：{bundled_dir}")
        try:
            _copy_bundled_platform_tools(INSTALL_DIR, progress_callback)
            log("内置资料复制完成")
        except FileNotFoundError as e:
            return False, str(e)
    else:
        log(f"检测到已存在安装目录：{INSTALL_DIR}")

    ok, version_or_err = _verify_adb(INSTALLED_ADB_EXE)
    if not ok:
        return False, f"安装后验证失败：{version_or_err}"

    log(version_or_err)
    if _is_path_in_user_path(INSTALL_DIR):
        log("PATH 中已包含 platform-tools 目录")
    else:
        log("正在将 platform-tools 加入用户 PATH...")
        added = _add_to_user_path(INSTALL_DIR)
        if added:
            log("已成功加入用户 PATH")
        else:
            log("PATH 已存在相同目录，无需重复添加")

    return True, (
        "ADB 环境安装完成。\n"
        f"安装路径：{INSTALL_DIR}\n"
        f"{version_or_err}\n\n"
        "提示：若其他已打开的终端或程序仍找不到 adb，请重新打开后再试。"
    )


class AdbInstallerWindow(ctk.CTkToplevel):
    """ADB 环境安装窗口：打开后自动执行安装与配置。"""

    def __init__(self, master):
        super().__init__(master)
        self.title("ADB 环境安装")
        self.geometry("560x420")
        self.resizable(True, True)
        self._installing = False
        self._build_ui()
        self.after(200, self._start_install)

    def _build_ui(self):
        title = ctk.CTkLabel(
            self,
            text="ADB 环境自动安装与配置",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(pady=(20, 8))

        hint = ctk.CTkLabel(
            self,
            text="使用软件内置 Platform-Tools，安装到本机并加入用户 PATH",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        hint.pack(pady=(0, 12))

        self._status_label = ctk.CTkLabel(
            self,
            text="准备中...",
            font=ctk.CTkFont(size=13),
            anchor="w",
            justify="left",
        )
        self._status_label.pack(fill="x", padx=24)

        self._progress = ctk.CTkProgressBar(self, mode="determinate")
        self._progress.pack(fill="x", padx=24, pady=(12, 8))
        self._progress.set(0)

        self._log_box = ctk.CTkTextbox(self, height=220, font=ctk.CTkFont(size=12))
        self._log_box.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        self._log_box.configure(state="disabled")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 20))

        self._btn_retry = ctk.CTkButton(
            btn_row,
            text="重新安装",
            width=120,
            command=lambda: self._start_install(force=True),
            state="disabled",
        )
        self._btn_retry.pack(side="right", padx=(8, 0))

        self._btn_close = ctk.CTkButton(
            btn_row,
            text="关闭",
            width=120,
            command=self.destroy,
        )
        self._btn_close.pack(side="right")

    def _append_log(self, text):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _set_status(self, text):
        self._status_label.configure(text=text)

    def _set_progress(self, value):
        self._progress.set(max(0.0, min(1.0, value)))

    def _ui(self, func, *args):
        self.after(0, lambda: func(*args))

    def _start_install(self, force=False):
        if self._installing:
            return
        self._installing = True
        self._btn_retry.configure(state="disabled")
        self._set_progress(0)
        self._set_status("正在安装...")
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

        def worker():
            try:
                ok, message = install_adb_environment(
                    log_callback=lambda msg: self._ui(self._append_log, msg),
                    progress_callback=lambda p: self._ui(self._set_progress, p),
                    force=force,
                )
                if ok:
                    self._ui(self._set_status, "安装完成")
                    self._ui(self._set_progress, 1.0)
                    self._ui(messagebox.showinfo, "完成", message)
                else:
                    self._ui(self._set_status, "安装失败")
                    self._ui(self._append_log, message)
                    self._ui(messagebox.showerror, "安装失败", message)
            except Exception as e:
                err = f"安装过程出错：{e}"
                self._ui(self._set_status, "安装失败")
                self._ui(self._append_log, err)
                self._ui(messagebox.showerror, "安装失败", err)
            finally:
                def done():
                    self._installing = False
                    self._btn_retry.configure(state="normal")

                self._ui(done)

        threading.Thread(target=worker, daemon=True).start()
