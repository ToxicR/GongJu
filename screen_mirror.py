# -*- coding: utf-8 -*-
"""
Android 投屏模块
优先使用 PyDroidCTRL + scrcpy 视频流（流畅）；未安装时回退到 ADB 截屏预览。
参考: https://pypi.org/project/PyDroidCTRL/
"""
import asyncio
import io
import os
import queue
import re
import subprocess
import sys
import threading
import time

import customtkinter as ctk
from tkinter import messagebox, Canvas
from PIL import Image, ImageTk

from log_viewer import find_adb, check_android_device

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_PREVIEW_FPS = 8
_POLL_MS = 50

# 可选：PyDroidCTRL（需 pip install PyDroidCTRL，且本机已安装 scrcpy）
# 官方示例: from android_controller import Controller
try:
    from android_controller import Controller as PyDroidController
except ImportError:
    try:
        from PyDroidCTRL.android_controller import Controller as PyDroidController
    except ImportError:
        PyDroidController = None


def find_scrcpy():
    """查找本机 scrcpy 可执行文件路径"""
    names = ["scrcpy.exe", "scrcpy"] if sys.platform == "win32" else ["scrcpy"]
    for name in names:
        try:
            r = subprocess.run(
                [name, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=_CREATIONFLAGS,
            )
            if r.returncode == 0 or "scrcpy" in (r.stdout or r.stderr or "").lower():
                return name
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    if sys.platform == "win32":
        for base in [
            os.path.expandvars(r"%LOCALAPPDATA%"),
            os.path.expanduser("~"),
        ]:
            for rel in [
                os.path.join("scoop", "apps", "scrcpy", "current", "scrcpy.exe"),
                os.path.join("scrcpy", "scrcpy.exe"),
            ]:
                path = os.path.join(base, rel)
                if os.path.isfile(path):
                    return path
    return None


def get_device_size(adb_cmd):
    """获取设备分辨率 (width, height)"""
    try:
        r = subprocess.run(
            [adb_cmd, "shell", "wm", "size"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_CREATIONFLAGS,
        )
        if r.returncode != 0:
            return None
        m = re.search(r"(\d+)\s*[x×]\s*(\d+)", (r.stdout or "") + (r.stderr or ""))
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


def capture_one_png(adb_cmd):
    """执行一次 PNG 截屏，返回 (PIL.Image, width, height) 或 None"""
    try:
        r = subprocess.run(
            [adb_cmd, "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=8,
            creationflags=_CREATIONFLAGS,
        )
        if r.returncode != 0 or not r.stdout:
            return None
        img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
        w, h = img.size
        return (img, w, h)
    except Exception:
        return None


def send_tap(adb_cmd, x, y):
    """在设备上执行点击 (x, y)"""
    if not adb_cmd:
        return False
    try:
        r = subprocess.run(
            [adb_cmd, "shell", "input", "tap", str(int(x)), str(int(y))],
            capture_output=True,
            timeout=5,
            creationflags=_CREATIONFLAGS,
        )
        return r.returncode == 0
    except Exception:
        return False


def _run_pydroid_stream(adb_path, scrcpy_path):
    """在后台线程中运行 PyDroidCTRL 的 scrcpy 视频流"""
    async def _stream():
        try:
            controller = PyDroidController(adb_path=adb_path, scrcpy_path=scrcpy_path)
            await controller.stream(
                max_fps=30,
                bit_rate="8M",
                rotate=False,
                always_on_top=False,
                disable_screensaver=True,
                no_audio=True,
            )
        except Exception:
            pass

    try:
        asyncio.run(_stream())
    except Exception:
        pass


class ScreenMirrorWindow(ctk.CTkToplevel):
    """投屏窗口：可选 PyDroidCTRL 视频流（scrcpy）或截屏预览"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("Android 投屏")
        self.geometry("900x680")
        self.resizable(True, True)
        _icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.isfile(_icon):
            try:
                self.iconbitmap(_icon)
            except Exception:
                pass

        self._adb_cmd = None
        self._device_size = None
        self._running = False
        self._thread = None
        self._frame_queue = queue.Queue(maxsize=1)
        self._photo = None
        self._display_w = 800
        self._display_h = 600
        self._offset_x = 0
        self._offset_y = 0
        self._shown_w = 0
        self._shown_h = 0
        self._orig_w = 0
        self._orig_h = 0
        self._scrcpy_path = find_scrcpy()
        self._pydroid_ok = PyDroidController is not None and self._scrcpy_path is not None

        self._build_ui()
        self._init_connection()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=8)

        self._status_label = ctk.CTkLabel(top, text="正在检测设备…", font=ctk.CTkFont(size=13))
        self._status_label.pack(side="left")

        # 视频流按钮（PyDroidCTRL + scrcpy）
        self._btn_stream = ctk.CTkButton(
            top,
            text="启动视频流投屏（scrcpy）",
            width=180,
            command=self._start_video_stream,
            state="disabled",
        )
        self._btn_stream.pack(side="right", padx=4)

        self._btn_toggle = ctk.CTkButton(
            top, text="开始预览（截屏）", width=140, command=self._toggle_stream, state="disabled"
        )
        self._btn_toggle.pack(side="right", padx=4)

        self._preview_frame = ctk.CTkFrame(self, fg_color=("#333", "#222"))
        self._preview_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._canvas = Canvas(
            self._preview_frame,
            bg="#1a1a1a",
            highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        self._hint = ctk.CTkLabel(
            self._preview_frame,
            text="使用「启动视频流投屏」可获得流畅画面（需安装 scrcpy）；或使用「开始预览」截屏方式",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self._hint.place(relx=0.5, rely=0.5, anchor="center")

    def _on_canvas_resize(self, event):
        self._display_w = max(100, event.width)
        self._display_h = max(100, event.height)

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
        ok, _ = check_android_device(self._adb_cmd)
        if not ok:
            self._set_status("未检测到设备")
            messagebox.showwarning(
                "未检测到设备",
                "请连接 Android 设备并开启 USB 调试。",
                parent=self,
            )
            return
        self._device_size = get_device_size(self._adb_cmd)
        self._set_status("设备已连接")
        self._btn_toggle.configure(state="normal")
        if self._pydroid_ok:
            self._btn_stream.configure(state="normal")
        else:
            if PyDroidController is None:
                self._set_status("设备已连接（可 pip install PyDroidCTRL 并安装 scrcpy 使用视频流）")
            elif not self._scrcpy_path:
                self._set_status("设备已连接（请安装 scrcpy 以使用视频流，如 winget install scrcpy）")

    def _start_video_stream(self):
        """使用 PyDroidCTRL 启动 scrcpy 视频流（独立窗口）"""
        if not self._pydroid_ok or not self._adb_cmd or not self._scrcpy_path:
            messagebox.showinfo(
                "使用视频流",
                "请先安装：\n1. pip install PyDroidCTRL\n2. scrcpy（如 winget install scrcpy）",
                parent=self,
            )
            return
        try:
            t = threading.Thread(
                target=_run_pydroid_stream,
                args=(self._adb_cmd, self._scrcpy_path),
                daemon=True,
            )
            t.start()
            self._set_status("已启动视频流，请到 scrcpy 窗口查看并操作设备")
        except Exception as e:
            messagebox.showerror("启动失败", str(e), parent=self)

    def _on_close(self):
        if self._running:
            self._stop_stream()
        self.destroy()

    def _toggle_stream(self):
        if self._running:
            self._stop_stream()
        else:
            self._start_stream()

    def _start_stream(self):
        if not self._adb_cmd:
            return
        self._running = True
        self._btn_toggle.configure(text="停止预览（截屏）")
        self._hint.place_forget()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        self._set_status("预览中（约 %d 帧/秒）· 在画面中点击可操作设备" % _PREVIEW_FPS)
        self._poll_queue()

    def _stop_stream(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.5)
            self._thread = None
        self._btn_toggle.configure(text="开始预览（截屏）")
        self._set_status("已停止")
        try:
            while True:
                self._frame_queue.get_nowait()
        except queue.Empty:
            pass
        self._hint.place(relx=0.5, rely=0.5, anchor="center")

    def _capture_loop(self):
        interval = 1.0 / _PREVIEW_FPS
        while self._running and self._adb_cmd:
            t0 = time.monotonic()
            result = capture_one_png(self._adb_cmd)
            if result is None:
                time.sleep(interval)
                continue
            img, orig_w, orig_h = result
            dw = getattr(self, "_display_w", 800)
            dh = getattr(self, "_display_h", 600)
            if dw <= 0 or dh <= 0:
                dw, dh = 800, 600
            iw, ih = img.size
            scale = min(dw / iw, dh / ih) if (iw and ih) else 1.0
            nw, nh = int(iw * scale), int(ih * scale)
            if nw <= 0 or nh <= 0:
                time.sleep(interval)
                continue
            resized = img.resize((nw, nh), Image.Resampling.BILINEAR)
            payload = (resized, orig_w, orig_h, nw, nh)
            try:
                self._frame_queue.put_nowait(payload)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                self._frame_queue.put_nowait(payload)
            elapsed = time.monotonic() - t0
            if elapsed < interval:
                time.sleep(interval - elapsed)

    def _poll_queue(self):
        if not self._running:
            return
        try:
            payload = self._frame_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            resized, self._orig_w, self._orig_h, self._shown_w, self._shown_h = payload
            w, h = self._display_w, self._display_h
            self._offset_x = (w - self._shown_w) // 2
            self._offset_y = (h - self._shown_h) // 2
            self._photo = resized
            if self._photo:
                self._photo_tk = ImageTk.PhotoImage(self._photo)
                self._canvas.delete("all")
                self._canvas.create_image(
                    self._offset_x, self._offset_y,
                    image=self._photo_tk, anchor="nw",
                )
            if not self._device_size and self._orig_w and self._orig_h:
                self._device_size = (self._orig_w, self._orig_h)
        self.after(_POLL_MS, self._poll_queue)

    def _on_click(self, event):
        if not self._running or not self._adb_cmd or not self._shown_w or not self._shown_h:
            return
        scale = self._orig_w / self._shown_w if self._shown_w else 1.0
        dx = (event.x - self._offset_x) * scale
        dy = (event.y - self._offset_y) * scale
        if self._device_size:
            dw, dh = self._device_size
            dx = max(0, min(dw - 1, dx))
            dy = max(0, min(dh - 1, dy))
        send_tap(self._adb_cmd, dx, dy)
