# -*- coding: utf-8 -*-
"""
Android 投屏模块。

提供两种模式：
1. 流畅投屏（scrcpy）：把 scrcpy 原生窗口嵌入软件内，视频解码与输入控制交给 scrcpy。
2. 兼容预览（截屏）：定时用 adb screencap 抓取完整画面渲染，鼠标/键盘经 adb input 控制。
   适用于 scrcpy 硬件编码器有问题、画面残缺的设备（如部分 rk3288 工控机）。
"""
import ctypes
import io
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from ctypes import wintypes
from datetime import datetime

import customtkinter as ctk
from tkinter import Canvas, messagebox

from log_viewer import check_android_device, find_adb

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except Exception:
    _PIL_OK = False

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_SCRCPY_MAX_SIZE = "1280"
_SCRCPY_MAX_FPS = "60"
_SCRCPY_DEFAULT_BIT_RATE = "8M"
_SCRCPY_BIT_RATE_OPTIONS = ["4M", "8M", "12M", "16M", "24M"]
_SCRCPY_EMBED_TIMEOUT = 8.0

# 兼容预览抓帧间隔（秒）。screencap 本身较慢，这里只做轻微节流。
_SCREENCAP_MIN_INTERVAL = 0.03
# 判定为点击（而非滑动）的像素阈值（设备坐标）。
_TAP_MOVE_THRESHOLD = 10

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM) if sys.platform == "win32" else None
_LOG_DIR = os.path.join(os.path.expandvars(r"%LOCALAPPDATA%"), "GongJu", "logs") if sys.platform == "win32" else os.path.join(os.path.expanduser("~"), ".gongju", "logs")
_MIRROR_LOG = os.path.join(_LOG_DIR, "screen_mirror.log")

# 键名 -> Android keyevent 码，用于兼容预览模式下的键盘控制。
_KEYEVENT_MAP = {
    "BackSpace": "67",
    "Return": "66",
    "KP_Enter": "66",
    "Tab": "61",
    "Escape": "111",
    "space": "62",
    "Left": "21",
    "Right": "22",
    "Up": "19",
    "Down": "20",
    "Delete": "112",
    "Home": "122",
    "End": "123",
    "Prior": "92",
    "Next": "93",
}


def _app_base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _adb_serial_args(serial):
    return ["-s", serial] if serial else []


def _run_no_window(args, **kwargs):
    return subprocess.run(args, creationflags=_CREATIONFLAGS, **kwargs)


def _log(message):
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(_MIRROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def _format_cmd(args):
    return " ".join(f'"{arg}"' if any(ch.isspace() for ch in str(arg)) else str(arg) for arg in args)


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
    """获取设备物理分辨率 (width, height)。"""
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


def get_current_display_size(adb_cmd, serial=None):
    """获取当前逻辑显示尺寸，优先使用已旋转后的 WindowManager cur=WxH。"""
    try:
        r = _run_no_window(
            [adb_cmd] + _adb_serial_args(serial) + ["shell", "dumpsys", "window", "displays"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        text = (r.stdout or "") + (r.stderr or "")
        m = re.search(r"\bcur=(\d+)x(\d+)\b", text)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass

    try:
        r = _run_no_window(
            [adb_cmd] + _adb_serial_args(serial) + ["shell", "dumpsys", "display"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        text = (r.stdout or "") + (r.stderr or "")
        m = re.search(r"mOverrideDisplayInfo=.*?\breal\s+(\d+)\s+x\s+(\d+)", text, re.S)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass

    return get_device_size(adb_cmd, serial)


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

    def embed(self, child_hwnd, parent_hwnd, x, y, width, height):
        style = int(self._get_window_long(child_hwnd, self.GWL_STYLE) or 0)
        style |= self.WS_CHILD | self.WS_VISIBLE
        style &= ~(self.WS_CAPTION | self.WS_THICKFRAME | self.WS_MINIMIZE | self.WS_MAXIMIZE | self.WS_SYSMENU)
        self._set_window_long(child_hwnd, self.GWL_STYLE, ctypes.c_void_p(style))
        self.user32.SetParent(child_hwnd, parent_hwnd)
        self.resize(child_hwnd, x, y, width, height)

    def resize(self, child_hwnd, x, y, width, height):
        x = int(x)
        y = int(y)
        width = max(1, int(width))
        height = max(1, int(height))
        self.user32.SetWindowPos(
            child_hwnd,
            None,
            x,
            y,
            width,
            height,
            self.SWP_NOZORDER | self.SWP_FRAMECHANGED,
        )
        self.user32.MoveWindow(child_hwnd, x, y, width, height, True)


class ScreenMirrorWindow(ctk.CTkToplevel):
    """投屏窗口：支持 scrcpy 流畅投屏与 screencap 兼容预览两种模式。"""

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
        self._physical_size = None
        self._device_size = None
        self._display_w = 800
        self._display_h = 600

        # scrcpy 模式状态
        self._scrcpy_path = find_scrcpy()
        self._scrcpy_process = None
        self._scrcpy_hwnd = None
        self._scrcpy_title = None
        self._scrcpy_output_thread = None
        self._scrcpy_texture_size = None
        self._embedder = _Win32WindowEmbedder() if sys.platform == "win32" else None
        self._bit_rate_var = ctk.StringVar(value=_SCRCPY_DEFAULT_BIT_RATE)

        # 兼容预览（screencap）模式状态
        self._cap_running = False
        self._cap_stop = threading.Event()
        self._cap_thread = None
        self._cap_photo = None
        self._cap_image_item = None
        self._cap_device_size = None      # 抓到的画面尺寸 = 设备分辨率 (w, h)
        self._cap_render = None           # (offset_x, offset_y, scale)，用于坐标映射
        self._cap_drag_start = None
        self._input_queue = queue.Queue()
        self._input_worker = None

        self._build_ui()
        self._init_connection()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=8)

        self._status_label = ctk.CTkLabel(top, text="正在检测设备...", font=ctk.CTkFont(size=13))
        self._status_label.pack(side="left")

        self._btn_scrcpy = ctk.CTkButton(
            top,
            text="启动流畅投屏",
            width=130,
            command=self._toggle_scrcpy,
            state="disabled",
        )
        self._btn_scrcpy.pack(side="right", padx=4)

        self._btn_screencap = ctk.CTkButton(
            top,
            text="兼容预览(截屏)",
            width=130,
            command=self._toggle_screencap,
            state="disabled",
        )
        self._btn_screencap.pack(side="right", padx=4)

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
            text=(
                "流畅投屏：scrcpy 低延迟视频+控制（个别工控机硬件编码器有问题时画面可能残缺）。\n"
                "兼容预览：adb 截屏渲染，画面完整但帧率较低，鼠标/键盘经 adb 控制。\n"
                f"日志：{_MIRROR_LOG}"
            ),
            font=ctk.CTkFont(size=12),
            text_color="gray",
            justify="center",
        )
        self._hint.place(relx=0.5, rely=0.5, anchor="center")

    def _on_canvas_resize(self, event):
        self._display_w = max(100, event.width)
        self._display_h = max(100, event.height)
        if self._scrcpy_hwnd and self._embedder:
            self._place_scrcpy_window()

    def _set_status(self, text):
        self._status_label.configure(text=text)

    # ------------------------------------------------------------ 连接初始化
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

        ok, _msg_or_devices = check_android_device(self._adb_cmd)
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
        self._physical_size = get_device_size(self._adb_cmd, self._serial)
        self._device_size = get_current_display_size(self._adb_cmd, self._serial) or self._physical_size
        _log(
            f"init adb={self._adb_cmd!r} scrcpy={self._scrcpy_path!r} serials={serials!r} "
            f"selected={self._serial!r} wm_size={self._physical_size!r} current_display={self._device_size!r} "
            f"pil={_PIL_OK}"
        )

        # 兼容预览只需 adb + PIL，跨平台可用。
        if _PIL_OK:
            self._btn_screencap.configure(state="normal")

        if self._scrcpy_path and self._embedder:
            self._btn_scrcpy.configure(state="normal")

        multi = f"已连接 {len(serials)} 台设备，默认使用 {self._serial}；" if len(serials) > 1 else "设备已连接；"
        if self._scrcpy_path and self._embedder:
            self._set_status(multi + "可启动流畅投屏或兼容预览")
        elif not self._scrcpy_path:
            self._set_status(multi + "未找到 scrcpy，可用兼容预览")
        else:
            self._set_status(multi + "当前系统不支持嵌入式 scrcpy，可用兼容预览")

    def _get_selected_bit_rate(self):
        bit_rate = (self._bit_rate_var.get() or _SCRCPY_DEFAULT_BIT_RATE).strip()
        return bit_rate if bit_rate in _SCRCPY_BIT_RATE_OPTIONS else _SCRCPY_DEFAULT_BIT_RATE

    # ============================================================ scrcpy 模式
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
        if self._cap_running:
            self._stop_screencap()

        self.update_idletasks()
        bit_rate = self._get_selected_bit_rate()
        self._log_device_diagnostics()
        self._scrcpy_texture_size = None
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
            if self._serial:
                env["ANDROID_SERIAL"] = self._serial
            scrcpy_cwd = os.path.dirname(os.path.abspath(self._scrcpy_path)) if os.path.isfile(self._scrcpy_path) else None
            _log(f"scrcpy command: {_format_cmd(args)}")
            _log(
                f"scrcpy cwd: {scrcpy_cwd!r}, SCRCPY_ADB={env.get('SCRCPY_ADB')!r}, "
                f"ANDROID_SERIAL={env.get('ANDROID_SERIAL')!r}"
            )
            self._scrcpy_process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=scrcpy_cwd,
                env=env,
                creationflags=_CREATIONFLAGS,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            self._scrcpy_output_thread = threading.Thread(
                target=self._read_scrcpy_output,
                args=(self._scrcpy_process,),
                daemon=True,
            )
            self._scrcpy_output_thread.start()
        except Exception as e:
            _log(f"start failed: {e!r}")
            messagebox.showerror("启动失败", str(e), parent=self)
            return

        _log(
            f"start selected bit_rate={bit_rate} "
            f"physical_size={self._physical_size!r} current_display={self._device_size!r} "
            f"canvas={self._display_w}x{self._display_h}"
        )
        self._hint.place_forget()
        self._btn_scrcpy.configure(text="停止流畅投屏")
        self._btn_screencap.configure(state="disabled")
        self._bit_rate_menu.configure(state="disabled")
        self._set_status("正在启动 scrcpy 视频流...")
        self.after(100, self._wait_and_embed_scrcpy, time.monotonic())

    def _read_scrcpy_output(self, proc):
        try:
            if not proc.stdout:
                return
            for raw_line in proc.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue
                _log(f"scrcpy output: {line}")
                match = re.search(r"\bTexture:\s*(\d+)x(\d+)\b", line)
                if match:
                    texture_size = (int(match.group(1)), int(match.group(2)))
                    self._scrcpy_texture_size = texture_size
                    _log(f"scrcpy texture parsed={texture_size!r}")
                    try:
                        self.after(0, self._place_scrcpy_window)
                    except Exception:
                        pass
        except Exception as e:
            _log(f"scrcpy output reader failed: {e!r}")

    def _log_device_diagnostics(self):
        if not self._adb_cmd:
            return
        _log("device diagnostics begin")
        commands = [
            ("wm size", ("shell", "wm", "size")),
            ("wm density", ("shell", "wm", "density")),
            ("dumpsys display", ("shell", "dumpsys", "display")),
            ("dumpsys window displays", ("shell", "dumpsys", "window", "displays")),
        ]
        for label, args in commands:
            try:
                r = _run_no_window(
                    [self._adb_cmd] + _adb_serial_args(self._serial) + list(args),
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                text = (r.stdout or "") or (r.stderr or "")
            except Exception as e:
                text = f"<error: {e!r}>"
            if len(text) > 5000:
                text = text[:5000] + "\n...[truncated]"
            _log(f"adb {label}: {text}")
        _log("device diagnostics end")

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
            x, y, w, h = self._get_scrcpy_rect()
            _log(
                f"embed hwnd={hwnd} parent={parent_hwnd} rect=({x},{y},{w},{h}) "
                f"canvas={self._display_w}x{self._display_h} texture={self._scrcpy_texture_size!r}"
            )
            self._embedder.embed(hwnd, parent_hwnd, x, y, w, h)
            # 首帧后 SDL 有时未及时按新尺寸重排，延迟再放置一次强制其重新布局。
            self.after(300, self._place_scrcpy_window)
            self._set_status(
                f"流畅投屏中（scrcpy {_SCRCPY_MAX_FPS} FPS 上限，{self._get_selected_bit_rate()}）"
            )
            self.after(1000, self._monitor_scrcpy)
            return

        if time.monotonic() - started_at >= _SCRCPY_EMBED_TIMEOUT:
            self._set_status("未能嵌入 scrcpy 窗口，已停止")
            _log("embed timeout")
            self._stop_scrcpy()
            return
        self.after(100, self._wait_and_embed_scrcpy, started_at)

    def _get_scrcpy_rect(self):
        canvas_w = max(1, self._display_w)
        canvas_h = max(1, self._display_h)
        if self._scrcpy_texture_size:
            device_w, device_h = self._scrcpy_texture_size
        elif self._device_size:
            device_w, device_h = self._device_size
        else:
            return 0, 0, canvas_w, canvas_h
        if device_w <= 0 or device_h <= 0:
            return 0, 0, canvas_w, canvas_h

        scale = min(canvas_w / device_w, canvas_h / device_h)
        target_w = max(1, int(device_w * scale))
        target_h = max(1, int(device_h * scale))
        x = (canvas_w - target_w) // 2
        y = (canvas_h - target_h) // 2
        return x, y, target_w, target_h

    def _place_scrcpy_window(self):
        if not self._scrcpy_hwnd or not self._embedder:
            return
        x, y, w, h = self._get_scrcpy_rect()
        self._embedder.resize(self._scrcpy_hwnd, x, y, w, h)

    def _monitor_scrcpy(self):
        if not self._scrcpy_process:
            return
        if self._scrcpy_process.poll() is not None:
            _log(f"scrcpy exited returncode={self._scrcpy_process.returncode}")
            self._scrcpy_process = None
            self._scrcpy_hwnd = None
            self._scrcpy_title = None
            self._scrcpy_output_thread = None
            self._scrcpy_texture_size = None
            self._cleanup_scrcpy_ui()
            self._set_status("scrcpy 已退出")
            return
        self.after(1000, self._monitor_scrcpy)

    def _stop_scrcpy(self):
        proc = self._scrcpy_process
        self._scrcpy_process = None
        self._scrcpy_hwnd = None
        self._scrcpy_title = None
        self._scrcpy_output_thread = None
        self._scrcpy_texture_size = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if proc:
            _log(f"stop scrcpy returncode={proc.poll()}")
        self._cleanup_scrcpy_ui()
        self._set_status("流畅投屏已停止")

    def _cleanup_scrcpy_ui(self):
        self._btn_scrcpy.configure(text="启动流畅投屏")
        self._bit_rate_menu.configure(state="normal")
        if _PIL_OK:
            self._btn_screencap.configure(state="normal")
        if not self._cap_running:
            self._hint.place(relx=0.5, rely=0.5, anchor="center")

    # ====================================================== 兼容预览(截屏)模式
    def _toggle_screencap(self):
        if self._cap_running:
            self._stop_screencap()
        else:
            self._start_screencap()

    def _start_screencap(self):
        if not _PIL_OK:
            messagebox.showinfo("兼容预览", "缺少 Pillow 库，无法使用兼容预览。", parent=self)
            return
        if not self._adb_cmd:
            messagebox.showinfo("兼容预览", "未找到 ADB。", parent=self)
            return
        if self._scrcpy_process and self._scrcpy_process.poll() is None:
            self._stop_scrcpy()

        self._cap_running = True
        self._cap_stop.clear()
        self._cap_device_size = None
        self._cap_render = None
        self._cap_drag_start = None
        self._hint.place_forget()

        # 绑定鼠标/键盘 -> adb input
        self._canvas.bind("<ButtonPress-1>", self._on_cap_press)
        self._canvas.bind("<ButtonRelease-1>", self._on_cap_release)
        self._canvas.bind("<Key>", self._on_cap_key)
        self._canvas.focus_set()

        self._ensure_input_worker()
        self._cap_thread = threading.Thread(target=self._cap_loop, daemon=True)
        self._cap_thread.start()

        self._btn_screencap.configure(text="停止兼容预览")
        self._btn_scrcpy.configure(state="disabled")
        self._bit_rate_menu.configure(state="disabled")
        self._set_status("兼容预览中（adb 截屏，帧率较低，可鼠标/键盘控制）")
        _log(f"screencap start serial={self._serial!r}")

    def _stop_screencap(self):
        self._cap_running = False
        self._cap_stop.set()
        try:
            self._canvas.unbind("<ButtonPress-1>")
            self._canvas.unbind("<ButtonRelease-1>")
            self._canvas.unbind("<Key>")
        except Exception:
            pass
        if self._cap_image_item is not None:
            try:
                self._canvas.delete(self._cap_image_item)
            except Exception:
                pass
            self._cap_image_item = None
        self._cap_photo = None
        self._btn_screencap.configure(text="兼容预览(截屏)")
        if self._scrcpy_path and self._embedder:
            self._btn_scrcpy.configure(state="normal")
        self._bit_rate_menu.configure(state="normal")
        if not (self._scrcpy_process and self._scrcpy_process.poll() is None):
            self._hint.place(relx=0.5, rely=0.5, anchor="center")
            self._set_status("兼容预览已停止")
        _log("screencap stop")

    def _cap_loop(self):
        while not self._cap_stop.is_set():
            data = self._grab_screencap()
            if data:
                try:
                    img = Image.open(io.BytesIO(data))
                    img.load()
                    if img.mode not in ("RGB", "RGBA"):
                        img = img.convert("RGB")
                    self.after(0, self._render_cap_image, img)
                except Exception as e:
                    _log(f"screencap decode failed: {e!r}")
            else:
                self._cap_stop.wait(0.5)
            self._cap_stop.wait(_SCREENCAP_MIN_INTERVAL)

    def _grab_screencap(self):
        try:
            r = _run_no_window(
                [self._adb_cmd] + _adb_serial_args(self._serial) + ["exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=10,
            )
            if r.returncode != 0 or not r.stdout:
                return None
            return r.stdout
        except Exception as e:
            _log(f"screencap grab failed: {e!r}")
            return None

    def _render_cap_image(self, img):
        if not self._cap_running:
            return
        canvas_w = max(1, self._display_w)
        canvas_h = max(1, self._display_h)
        iw, ih = img.size
        if iw <= 0 or ih <= 0:
            return
        self._cap_device_size = (iw, ih)
        scale = min(canvas_w / iw, canvas_h / ih)
        disp_w = max(1, int(iw * scale))
        disp_h = max(1, int(ih * scale))
        offset_x = (canvas_w - disp_w) // 2
        offset_y = (canvas_h - disp_h) // 2
        self._cap_render = (offset_x, offset_y, scale)
        try:
            disp = img.resize((disp_w, disp_h), Image.BILINEAR)
            self._cap_photo = ImageTk.PhotoImage(disp)
        except Exception as e:
            _log(f"screencap render failed: {e!r}")
            return
        if self._cap_image_item is None:
            self._cap_image_item = self._canvas.create_image(
                offset_x, offset_y, anchor="nw", image=self._cap_photo
            )
        else:
            self._canvas.coords(self._cap_image_item, offset_x, offset_y)
            self._canvas.itemconfigure(self._cap_image_item, image=self._cap_photo)

    def _canvas_to_device(self, ex, ey):
        if not self._cap_render or not self._cap_device_size:
            return None
        offset_x, offset_y, scale = self._cap_render
        iw, ih = self._cap_device_size
        if scale <= 0:
            return None
        dx = int((ex - offset_x) / scale)
        dy = int((ey - offset_y) / scale)
        if dx < 0 or dy < 0 or dx >= iw or dy >= ih:
            return None
        return dx, dy

    def _on_cap_press(self, event):
        self._canvas.focus_set()
        self._cap_drag_start = (event.x, event.y, time.monotonic())

    def _on_cap_release(self, event):
        if not self._cap_drag_start:
            return
        sx, sy, st = self._cap_drag_start
        self._cap_drag_start = None
        p0 = self._canvas_to_device(sx, sy)
        if not p0:
            return
        p1 = self._canvas_to_device(event.x, event.y) or p0
        if abs(p1[0] - p0[0]) + abs(p1[1] - p0[1]) < _TAP_MOVE_THRESHOLD:
            self._queue_input(["input", "tap", str(p0[0]), str(p0[1])])
        else:
            duration = max(50, int((time.monotonic() - st) * 1000))
            self._queue_input(
                ["input", "swipe", str(p0[0]), str(p0[1]), str(p1[0]), str(p1[1]), str(duration)]
            )

    def _on_cap_key(self, event):
        if not self._cap_running:
            return
        keysym = event.keysym
        if keysym in _KEYEVENT_MAP:
            self._queue_input(["input", "keyevent", _KEYEVENT_MAP[keysym]])
            return
        ch = event.char
        if ch and len(ch) == 1 and ch.isprintable() and ch != " ":
            self._queue_input(["input", "text", ch])

    # ------------------------------------------------------ adb input 工作线程
    def _ensure_input_worker(self):
        if self._input_worker and self._input_worker.is_alive():
            return
        self._input_worker = threading.Thread(target=self._input_worker_loop, daemon=True)
        self._input_worker.start()

    def _queue_input(self, args):
        try:
            self._input_queue.put_nowait(args)
        except Exception:
            pass

    def _input_worker_loop(self):
        while True:
            args = self._input_queue.get()
            if args is None:
                return
            if not self._adb_cmd:
                continue
            try:
                _run_no_window(
                    [self._adb_cmd] + _adb_serial_args(self._serial) + ["shell"] + args,
                    capture_output=True,
                    timeout=5,
                )
            except Exception as e:
                _log(f"input cmd failed {args!r}: {e!r}")

    # ------------------------------------------------------------------ 关闭
    def _on_close(self):
        if self._cap_running:
            self._stop_screencap()
        if self._scrcpy_process and self._scrcpy_process.poll() is None:
            self._stop_scrcpy()
        try:
            self._input_queue.put_nowait(None)
        except Exception:
            pass
        self.destroy()
