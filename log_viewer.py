# -*- coding: utf-8 -*-
"""
Android 设备日志实时输出模块
通过 ADB 连接设备并实时显示 logcat 输出。
"""
import subprocess
import threading
import queue
import sys
import os
import re
import json
from datetime import datetime

# 保存包名列表的本地文件（与脚本同目录）
_PACKAGES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_viewer_packages.json")
_DEFAULT_PACKAGE = "com.jpgk.autobooth"


def _load_packages():
    """从本地文件加载已保存的包名列表"""
    try:
        if os.path.isfile(_PACKAGES_FILE):
            with open(_PACKAGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return []


def _save_packages(packages):
    """将包名列表保存到本地文件"""
    try:
        with open(_PACKAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(packages, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

import customtkinter as ctk
from tkinter import messagebox, filedialog

from adb_paths import INSTALLED_ADB_EXE, get_bundled_adb_exe

# 尝试使用 ADB，常见路径
ADB_NAMES = ["adb.exe", "adb"]


def find_adb():
    """查找系统可用的 adb 路径"""
    # 1. 环境变量 PATH 中的 adb
    for name in ADB_NAMES:
        try:
            r = subprocess.run(
                [name, "version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if r.returncode == 0:
                return name
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    # 2. 本机安装目录与常见 Android SDK 路径
    common_paths = [
        INSTALLED_ADB_EXE,
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
    ]
    bundled = get_bundled_adb_exe()
    if bundled:
        common_paths.append(bundled)
    for path in common_paths:
        if os.path.isfile(path):
            return path
    return None


def check_android_device(adb_cmd):
    """检查是否有已连接的 Android 设备"""
    try:
        r = subprocess.run(
            [adb_cmd, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if r.returncode != 0:
            return False, "执行 adb devices 失败"
        lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
        # 第一行是 "List of devices attached"
        devices = [l for l in lines[1:] if l and not l.startswith("*") and "\tdevice" in l]
        if not devices:
            return False, "未检测到已连接的 Android 设备，请连接设备并开启 USB 调试"
        return True, devices
    except Exception as e:
        return False, str(e)


def get_pid_by_package(adb_cmd, package):
    """根据包名获取应用进程 PID，未运行返回 None"""
    if not package or not package.strip():
        return None
    try:
        r = subprocess.run(
            [adb_cmd, "shell", "pidof", "-s", package.strip()],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if r.returncode != 0 or not r.stdout:
            return None
        pid = r.stdout.strip().split()[0] if r.stdout.strip() else None
        return pid if pid and pid.isdigit() else None
    except Exception:
        return None


class LogViewerWindow(ctk.CTkToplevel):
    """日志输出窗口：连接 Android 设备并实时显示 logcat"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("Android 日志实时输出")
        self.geometry("900x600")
        self.resizable(True, True)
        _icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.isfile(_icon):
            try:
                self.iconbitmap(_icon)
            except Exception:
                pass
        self._adb_cmd = None
        self._process = None
        self._thread = None
        self._stop_event = threading.Event()
        self._log_queue = queue.Queue()
        self._running = False
        self._filter_pid = None  # 用于本地按 PID 过滤（当设备不支持 --pid 时）
        self._saved_packages = []  # 本地保存的包名列表，用于下拉与持久化

        self._build_ui()
        self._check_adb_and_device()
        # 有设备时在下一帧自动开始实时输出（不依赖用户点击）
        if self._adb_cmd and not self._running:
            self.after(100, self._do_auto_start)

    def _build_ui(self):
        # 包名筛选行：下拉选择 + 可输入新包名 + 删除当前项
        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            filter_row,
            text="包名筛选：",
            font=ctk.CTkFont(size=13),
            width=70,
        ).pack(side="left", padx=(0, 6))
        self._saved_packages = _load_packages()
        if _DEFAULT_PACKAGE and _DEFAULT_PACKAGE not in self._saved_packages:
            self._saved_packages.insert(0, _DEFAULT_PACKAGE)
            _save_packages(self._saved_packages)
        self._package_combo = ctk.CTkComboBox(
            filter_row,
            values=self._saved_packages,
            height=28,
            font=ctk.CTkFont(size=13),
            width=320,
        )
        if self._saved_packages:
            self._package_combo.set(_DEFAULT_PACKAGE if _DEFAULT_PACKAGE in self._saved_packages else self._saved_packages[0])
        self._package_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._btn_del_package = ctk.CTkButton(
            filter_row,
            text="删除当前",
            width=70,
            fg_color="gray",
            command=self._delete_current_package,
        )
        self._btn_del_package.pack(side="left")

        # 顶部：状态与操作
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=12)

        self._status_label = ctk.CTkLabel(
            top,
            text="状态：就绪",
            font=ctk.CTkFont(size=13),
            anchor="w",
        )
        self._status_label.pack(side="left", fill="x", expand=True)

        self._btn_start = ctk.CTkButton(
            top,
            text="开始实时输出",
            width=120,
            command=self._start_logcat,
        )
        self._btn_start.pack(side="right", padx=(8, 0))

        self._btn_stop = ctk.CTkButton(
            top,
            text="停止输出",
            width=80,
            state="disabled",
            fg_color="gray",
            command=self._stop_logcat,
        )
        self._btn_stop.pack(side="right")

        # 导出按钮
        self._btn_export = ctk.CTkButton(
            top,
            text="导出",
            width=60,
            command=self._export_log,
        )
        self._btn_export.pack(side="right", padx=(0, 8))

        # 清空按钮
        self._btn_clear = ctk.CTkButton(
            top,
            text="清空",
            width=80,
            command=self._clear_log,
        )
        self._btn_clear.pack(side="right", padx=(0, 8))

        # 日志文本框（使用 tkinter 的 Text 以支持大量实时输出）
        log_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
        )
        self._log_text.pack(fill="both", expand=True)

    def _set_status(self, msg):
        self._status_label.configure(text=f"状态：{msg}")

    def _add_package_if_new(self, pkg):
        """若当前输入的包名不在已保存列表中则追加并保存、刷新下拉"""
        if not pkg or pkg in self._saved_packages:
            return
        self._saved_packages.append(pkg)
        _save_packages(self._saved_packages)
        self._package_combo.configure(values=self._saved_packages)
        self._package_combo.set(pkg)

    def _delete_current_package(self):
        """从已保存列表中删除当前选中的包名并刷新下拉"""
        pkg = (self._package_combo.get() or "").strip()
        if not pkg or pkg not in self._saved_packages:
            messagebox.showinfo("删除包名", "当前包名不在已保存列表中，无需删除。", parent=self)
            return
        self._saved_packages = [x for x in self._saved_packages if x != pkg]
        _save_packages(self._saved_packages)
        new_values = self._saved_packages if self._saved_packages else [""]
        self._package_combo.configure(values=new_values)
        self._package_combo.set(new_values[0])
        messagebox.showinfo("删除包名", f"已从列表中删除：{pkg}", parent=self)

    def _check_adb_and_device(self):
        """启动时检查 ADB 与设备"""
        self._adb_cmd = find_adb()
        if not self._adb_cmd:
            self._set_status("未找到 ADB，请安装 Android SDK 或将 adb 加入 PATH")
            self._btn_start.configure(state="disabled")
            messagebox.showerror(
                "错误",
                "未找到 ADB。请安装 Android SDK Platform-Tools，或将 adb 所在目录加入系统 PATH。",
                parent=self,
            )
            return
        ok, msg_or_devices = check_android_device(self._adb_cmd)
        if not ok:
            self._set_status(msg_or_devices)
            self._btn_start.configure(state="normal")  # 仍可尝试开始，可能用户稍后连接
            return
        self._set_status(f"已连接设备 {len(msg_or_devices)} 台，将自动开始实时输出日志。")

    def _do_auto_start(self):
        """窗口就绪后自动开始实时输出（仅当有设备且未在运行）"""
        if self._running or not self._adb_cmd:
            return
        try:
            ok, _ = check_android_device(self._adb_cmd)
            if ok:
                self._start_logcat()
        except Exception:
            pass

    def _start_logcat(self):
        """开始执行 adb logcat 并实时显示"""
        if self._running:
            return
        self._adb_cmd = self._adb_cmd or find_adb()
        if not self._adb_cmd:
            messagebox.showerror("错误", "未找到 ADB。", parent=self)
            return
        ok, _ = check_android_device(self._adb_cmd)
        if not ok:
            messagebox.showwarning(
                "未检测到设备",
                "未检测到已连接的 Android 设备。请连接设备并开启 USB 调试后再试。",
                parent=self,
            )
            return

        self._running = True
        self._stop_event.clear()
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")

        # 按包名筛选：统一用全量 logcat + 本地按 PID 过滤，兼容不支持 --pid 的设备
        pkg = (self._package_combo.get() or "").strip()
        self._add_package_if_new(pkg)
        self._filter_pid = None
        if pkg:
            pid = get_pid_by_package(self._adb_cmd, pkg)
            if pid:
                self._filter_pid = str(pid)
                self._set_status(f"正在实时输出日志（仅包名: {pkg}，pid={pid}）…")
            else:
                self._set_status(f"正在实时输出日志（未检测到「{pkg}」进程，显示全部）…")
                messagebox.showinfo(
                    "包名筛选",
                    f"未检测到应用「{pkg}」正在运行，将显示全部日志。\n请先启动该应用后，点击「停止输出」再「开始实时输出」即可只显示该应用日志。",
                    parent=self,
                )
        else:
            self._set_status("正在实时输出日志（全部进程）…")

        # 清空设备端日志缓冲区，只从当前时刻开始输出（不显示打开前的历史日志）
        try:
            subprocess.run(
                [self._adb_cmd, "logcat", "-c"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except Exception:
            pass

        # 始终使用全量 logcat，包名筛选在本地按 PID 过滤（兼容所有设备）
        logcat_args = [self._adb_cmd, "logcat", "-v", "time"]
        self._process = subprocess.Popen(
            logcat_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self._thread = threading.Thread(target=self._read_logcat_output, daemon=True)
        self._thread.start()
        self._poll_queue()

    def _read_logcat_output(self):
        """在子线程中按小块读取 logcat，实时放入队列（避免缓冲延迟）"""
        buf = b""
        try:
            while not self._stop_event.is_set() and self._process and self._process.stdout:
                chunk = self._process.stdout.read(256)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf or b"\r" in buf:
                    if b"\n" in buf:
                        line, _, buf = buf.partition(b"\n")
                    else:
                        line, _, buf = buf.partition(b"\r")
                    try:
                        text = line.decode("utf-8", errors="replace") + "\n"
                        # 包名为空时 _filter_pid 为 None，输出全部进程日志；否则只输出包含该 PID 的行
                        show = self._filter_pid is None or re.search(
                            r"\b" + re.escape(self._filter_pid) + r"\b", text
                        )
                        if not show and self._filter_pid and len(text.strip()) > 0:
                            low = text.lower()
                            if "logcat" in low or "error" in low or "usage" in low or "unrecognized" in low:
                                show = True  # 让 logcat 报错等系统信息可见
                        if show:
                            self._log_queue.put(text)
                    except Exception:
                        pass
            if buf:
                try:
                    text = buf.decode("utf-8", errors="replace")
                    show = self._filter_pid is None or re.search(
                        r"\b" + re.escape(self._filter_pid) + r"\b", text
                    )
                    if not show and self._filter_pid and len(text.strip()) > 0:
                        low = text.lower()
                        if "logcat" in low or "error" in low or "usage" in low or "unrecognized" in low:
                            show = True
                    if show:
                        self._log_queue.put(text)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._log_queue.put(None)  # 结束标记
        except Exception:
            pass

    # 每轮最多处理的日志行数，避免主线程长时间阻塞导致界面无响应
    _MAX_LINES_PER_POLL = 80

    def _poll_queue(self):
        """在主线程中从队列取数据写入文本框，每轮限制行数避免卡顿"""
        processed = 0
        try:
            while processed < self._MAX_LINES_PER_POLL:
                line = self._log_queue.get_nowait()
                if line is None:
                    self._on_logcat_finished()
                    return
                self._log_text.insert("end", line)
                processed += 1
        except queue.Empty:
            pass
        if processed > 0:
            self._log_text.see("end")
            self._log_text.update_idletasks()
        if self._running:
            self.after(10, self._poll_queue)

    def _on_logcat_finished(self):
        """logcat 进程结束后的处理"""
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._set_status("已停止。可点击「开始实时输出」继续。")

    def _stop_logcat(self):
        """用户点击停止"""
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass

    def _clear_log(self):
        """清空日志文本框"""
        self._log_text.delete("1.0", "end")

    def _export_log(self):
        """将当前文本框中的全部内容导出为文件，多条连续换行合并为一条"""
        content = self._log_text.get("1.0", "end")
        if not content or not content.strip():
            messagebox.showinfo("导出", "当前没有可导出的日志内容。", parent=self)
            return
        # 将连续多个换行符（\n、\r\n、\r）合并为单个 \n，避免每条日志之间多空行
        content = re.sub(r"[\r\n]+", "\n", content)
        path = filedialog.asksaveasfilename(
            parent=self,
            title="导出日志",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("日志文件", "*.log"), ("所有文件", "*.*")],
            initialfile=f"logcat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("导出", f"已导出全部日志到：\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("导出失败", str(e), parent=self)

    def destroy(self):
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        super().destroy()
