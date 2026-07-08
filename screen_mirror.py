# -*- coding: utf-8 -*-
"""
Android 投屏模块。

把 scrcpy 原生窗口嵌入到软件内，视频解码和输入控制交给 scrcpy。
"""
import ctypes
import os
import re
import subprocess
import sys
import time
import uuid
from ctypes import wintypes

import customtkinter as ctk
from tkinter import Canvas, messagebox

from log_viewer import check_android_device, find_adb

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_SCRCPY_MAX_SIZE = "1280"
_SCRCPY_MAX_FPS = "60"
_SCRCPY_DEFAULT_BIT_RATE = "8M"
_SCRCPY_BIT_RATE_OPTIONS = ["4M", "8M", "12M", "16M", "24M"]
_SCRCPY_EMBED_TIMEOUT = 8.0
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM) if sys.platform == "win32" else None


def _app_base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _adb_serial_args(serial):
    return ["-s", serial] if serial else []


def _run_no_window(args, **kwargs):
    return subprocess.run(args, creationflags=_CREATIONFLAGS, **kwargs)


def find_scrcpy():
    """查找本机 scrcpy 可执行文件。"""
    candidates = []
    if sys.platform == "win32":
        base = _app_base_dir()
        candidates.extend(
            [
                os.path.join(base, "scrcpy.exe"),
                os.path.join(base, "bundled", "scrcpy", "scrcpy.exe"),
                os.path.join(os.path.dirname(base), "scrcpy", "scrcpy.exe"),
                os.path.join(os.path.expandvars(r"%LOCALAPPDATA%"), "scrcpy", "scrcpy.exe"),
                os.path.join(os.path.expanduser("~"), "scoop", "apps", "scrcpy", "current", "scrcpy.exe"),
            ]
        )

    names = ["scrcpy.exe", "scrcpy"] if sys.platform == "win32" else ["scrcpy"]
    for name in names:
        try:
            r = _run_no_window(
                [name, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0 or "scrcpy" in (r.stdout or r.stderr or "").lower():
                return name
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def get_connected_serials(adb_cmd):
    """返回 adb devices 中状态为 device 的设备序列号。"""
    try:
        r = _run_no_window(
            [adb_cmd, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return []
        serials = []
        for line in (r.stdout or "").splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
        return serials
    except Exception:
        return []


def get_device_size(adb_cmd, serial=None):
    """获取设备分辨率 (width, height)。"""
    try:
        r = _run_no_window(
            [adb_cmd] + _adb_serial_args(serial) + ["shell", "wm", "size"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return None
        m = re.search(r"(\d+)\s*[x×]\s*(\d+)", (r.stdout or "") + (r.stderr or ""))
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


class _Win32WindowEmbedder:
    """把外部顶层窗口重设为指定 HWND 的子窗口。"""

    GWL_STYLE = -16
    WS_CHILD = 0x40000000
    WS_VISIBLE = 0x10000000
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_MINIMIZE = 0x20000000
    WS_MAXIMIZE = 0x01000000
    WS_SYSMENU = 0x00080000
    SWP_NOZORDER = 0x0004
    SWP_FRAMECHANGED = 0x0020

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("嵌入式 scrcpy 目前只支持 Windows")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._setup_signatures()

    def _setup_signatures(self):
        self.user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        self.user32.SetParent.restype = wintypes.HWND
        self.user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL]
        self.user32.MoveWindow.restype = wintypes.BOOL
        self.user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self.user32.SetWindowPos.restype = wintypes.BOOL

        if hasattr(self.user32, "GetWindowLongPtrW"):
            self._get_window_long = self.user32.GetWindowLongPtrW
            self._set_window_long = self.user32.SetWindowLongPtrW
        else:
            self._get_window_long = self.user32.GetWindowLongW
            self._set_window_long = self.user32.SetWindowLongW
        self._get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
        self._get_window_long.restype = ctypes.c_void_p
        self._set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        self._set_window_long.restype = ctypes.c_void_p

    def find_window(self, pid, title):
        found = []

        def callback(hwnd, _):
            window_pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value != pid or not self.user32.IsWindowVisible(hwnd):
                return True
            length = self.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value == title:
                found.append(hwnd)
                return False
            return True

        enum_proc = _WNDENUMPROC(callback)
        self.user32.EnumWindows(enum_proc, 0)
        return found[0] if found else None

    def embed(self, child_hwnd, parent_hwnd, width, height):
        style = int(self._get_window_long(child_hwnd, self.GWL_STYLE) or 0)
        style |= self.WS_CHILD | self.WS_VISIBLE
        style &= ~(self.WS_CAPTION | self.WS_THICKFRAME | self.WS_MINIMIZE | self.WS_MAXIMIZE | self.WS_SYSMENU)
        self._set_window_long(child_hwnd, self.GWL_STYLE, ctypes.c_void_p(style))
        self.user32.SetParent(child_hwnd, parent_hwnd)
        self.resize(child_hwnd, width, height)

    def resize(self, child_hwnd, width, height):
        width = max(1, int(width))
        height = max(1, int(height))
        self.user32.SetWindowPos(
            child_hwnd,
            None,
            0,
            0,
            width,
            height,
            self.SWP_NOZORDER | self.SWP_FRAMECHANGED,
        )
        self.user32.MoveWindow(child_hwnd, 0, 0, width, height, True)


class ScreenMirrorWindow(ctk.CTkToplevel):
    """投屏窗口：嵌入 scrcpy 视频流。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("Android 投屏")
        self.geometry("900x680")
        self.resizable(True, True)
        icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.isfile(icon):
            try:
                self.iconbitmap(icon)
            except Exception:
                pass

        self._adb_cmd = None
        self._serial = None
        self._device_size = None
        self._display_w = 800
        self._display_h = 600

        self._scrcpy_path = find_scrcpy()
        self._scrcpy_process = None
        self._scrcpy_hwnd = None
        self._scrcpy_title = None
        self._embedder = _Win32WindowEmbedder() if sys.platform == "win32" else None
        self._bit_rate_var = ctk.StringVar(value=_SCRCPY_DEFAULT_BIT_RATE)

        self._build_ui()
        self._init_connection()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=8)

        self._status_label = ctk.CTkLabel(top, text="正在检测设备...", font=ctk.CTkFont(size=13))
        self._status_label.pack(side="left")

        self._btn_scrcpy = ctk.CTkButton(
            top,
            text="启动流畅投屏",
            width=140,
            command=self._toggle_scrcpy,
            state="disabled",
        )
        self._btn_scrcpy.pack(side="right", padx=4)

        self._bit_rate_menu = ctk.CTkOptionMenu(
            top,
            values=_SCRCPY_BIT_RATE_OPTIONS,
            variable=self._bit_rate_var,
            width=90,
        )
        self._bit_rate_menu.pack(side="right", padx=4)

        self._bit_rate_label = ctk.CTkLabel(top, text="码率", font=ctk.CTkFont(size=13))
        self._bit_rate_label.pack(side="right", padx=(12, 2))

        self._preview_frame = ctk.CTkFrame(self, fg_color=("#333", "#222"))
        self._preview_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._canvas = Canvas(self._preview_frame, bg="#1a1a1a", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        self._hint = ctk.CTkLabel(
            self._preview_frame,
            text="点击“启动流畅投屏”后，可在此窗口内预览并控制 Android 设备。",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self._hint.place(relx=0.5, rely=0.5, anchor="center")

    def _on_canvas_resize(self, event):
        self._display_w = max(100, event.width)
        self._display_h = max(100, event.height)
        if self._scrcpy_hwnd and self._embedder:
            self._embedder.resize(self._scrcpy_hwnd, self._display_w, self._display_h)

    def _set_status(self, text):
        self._status_label.configure(text=text)

    def _init_connection(self):
        self._adb_cmd = find_adb()
        if not self._adb_cmd:
            self._set_status("未找到 ADB")
            messagebox.showwarning(
                "未找到 ADB",
                "请安装 Android SDK Platform-Tools 或将 adb 加入 PATH。",
                parent=self,
            )
            return

        ok, msg_or_devices = check_android_device(self._adb_cmd)
        if not ok:
            self._set_status("未检测到设备")
            messagebox.showwarning(
                "未检测到设备",
                "请连接 Android 设备并开启 USB 调试。",
                parent=self,
            )
            return

        serials = get_connected_serials(self._adb_cmd)
        self._serial = serials[0] if serials else None
        self._device_size = get_device_size(self._adb_cmd, self._serial)

        if self._scrcpy_path and self._embedder:
            self._btn_scrcpy.configure(state="normal")
            if len(serials) > 1:
                self._set_status(f"已连接 {len(serials)} 台设备，默认使用 {self._serial}")
            else:
                self._set_status("设备已连接，可启动流畅投屏")
        elif not self._scrcpy_path:
            self._set_status("设备已连接；未找到 scrcpy，无法启动流畅投屏")
        else:
            self._set_status("设备已连接；当前系统不支持嵌入式 scrcpy")

    def _toggle_scrcpy(self):
        if self._scrcpy_process and self._scrcpy_process.poll() is None:
            self._stop_scrcpy()
        else:
            self._start_scrcpy()

    def _start_scrcpy(self):
        if not self._adb_cmd or not self._scrcpy_path:
            messagebox.showinfo("流畅投屏", "请先安装 scrcpy（如 winget install scrcpy）。", parent=self)
            return
        if not self._embedder:
            messagebox.showinfo("流畅投屏", "嵌入式 scrcpy 目前只支持 Windows。", parent=self)
            return

        self.update_idletasks()
        bit_rate = self._get_selected_bit_rate()
        self._scrcpy_title = f"Gongju scrcpy {uuid.uuid4().hex}"
        args = [
            self._scrcpy_path,
            "--no-audio",
            "--window-title",
            self._scrcpy_title,
            "--window-borderless",
            "--disable-screensaver",
            "--max-size",
            _SCRCPY_MAX_SIZE,
            "--max-fps",
            _SCRCPY_MAX_FPS,
            "--video-bit-rate",
            bit_rate,
        ]
        if self._serial:
            args.extend(["-s", self._serial])

        try:
            env = os.environ.copy()
            if self._adb_cmd:
                env["SCRCPY_ADB"] = self._adb_cmd
            scrcpy_cwd = os.path.dirname(os.path.abspath(self._scrcpy_path)) if os.path.isfile(self._scrcpy_path) else None
            self._scrcpy_process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=scrcpy_cwd,
                env=env,
                creationflags=_CREATIONFLAGS,
            )
        except Exception as e:
            messagebox.showerror("启动失败", str(e), parent=self)
            return

        self._hint.place_forget()
        self._btn_scrcpy.configure(text="停止流畅投屏")
        self._bit_rate_menu.configure(state="disabled")
        self._set_status("正在启动 scrcpy 视频流...")
        self.after(100, self._wait_and_embed_scrcpy, time.monotonic())

    def _get_selected_bit_rate(self):
        bit_rate = (self._bit_rate_var.get() or _SCRCPY_DEFAULT_BIT_RATE).strip()
        return bit_rate if bit_rate in _SCRCPY_BIT_RATE_OPTIONS else _SCRCPY_DEFAULT_BIT_RATE

    def _wait_and_embed_scrcpy(self, started_at):
        if not self._scrcpy_process:
            return
        if self._scrcpy_process.poll() is not None:
            self._set_status("scrcpy 已退出，请确认设备授权和 scrcpy 安装是否正常")
            self._cleanup_scrcpy_ui()
            return

        hwnd = self._embedder.find_window(self._scrcpy_process.pid, self._scrcpy_title)
        if hwnd:
            self._scrcpy_hwnd = hwnd
            parent_hwnd = self._canvas.winfo_id()
            self._embedder.embed(hwnd, parent_hwnd, self._display_w, self._display_h)
            self._set_status(f"流畅投屏中（scrcpy {_SCRCPY_MAX_FPS} FPS 上限，{self._get_selected_bit_rate()}）")
            self.after(1000, self._monitor_scrcpy)
            return

        if time.monotonic() - started_at >= _SCRCPY_EMBED_TIMEOUT:
            self._set_status("未能嵌入 scrcpy 窗口，已停止")
            self._stop_scrcpy()
            return
        self.after(100, self._wait_and_embed_scrcpy, started_at)

    def _monitor_scrcpy(self):
        if not self._scrcpy_process:
            return
        if self._scrcpy_process.poll() is not None:
            self._scrcpy_process = None
            self._scrcpy_hwnd = None
            self._scrcpy_title = None
            self._cleanup_scrcpy_ui()
            self._set_status("scrcpy 已退出")
            return
        self.after(1000, self._monitor_scrcpy)

    def _stop_scrcpy(self):
        proc = self._scrcpy_process
        self._scrcpy_process = None
        self._scrcpy_hwnd = None
        self._scrcpy_title = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._cleanup_scrcpy_ui()
        self._set_status("流畅投屏已停止")

    def _cleanup_scrcpy_ui(self):
        self._btn_scrcpy.configure(text="启动流畅投屏")
        self._bit_rate_menu.configure(state="normal")
        self._hint.place(relx=0.5, rely=0.5, anchor="center")

    def _on_close(self):
        if self._scrcpy_process and self._scrcpy_process.poll() is None:
            self._stop_scrcpy()
        self.destroy()
