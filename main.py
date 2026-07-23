# -*- coding: utf-8 -*-
"""
Windows 工具软件 - 主入口
左侧导航 + 右侧面板；日志/文件浏览器/投屏等重型功能仍打开独立窗口。
"""
import os

import customtkinter as ctk

from adb_util import find_adb, list_device_serials
from log_viewer import LogViewerWindow
from adb_file_browser import AdbFileBrowserWindow
from screen_mirror import ScreenMirrorWindow
from adb_installer import AdbInstallerWindow

from panels.base import LaunchPanel
from panels.device_info import DeviceInfoPanel
from panels.wireless_adb import WirelessAdbPanel
from panels.port_forward import PortForwardPanel
from panels.adb_shell import AdbShellPanel
from panels.app_manager import AppManagerPanel
from panels.media_capture import MediaCapturePanel
from panels.clipboard_history import ClipboardHistoryPanel
from panels.hash_tool import HashToolPanel
from panels.encoding_tool import EncodingToolPanel
from panels.timestamp_tool import TimestampToolPanel
from panels.json_tool import JsonToolPanel

_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# 导航：("section", 标题) 或 ("item", id, 标题)
_NAV = [
    ("section", "设备"),
    ("item", "device_info", "设备信息"),
    ("item", "wireless_adb", "无线 ADB"),
    ("item", "port_forward", "端口转发"),
    ("item", "adb_shell", "ADB Shell"),
    ("section", "应用与文件"),
    ("item", "app_manager", "应用管理"),
    ("item", "file_browser", "文件浏览器"),
    ("section", "调试与投屏"),
    ("item", "log_viewer", "日志输出"),
    ("item", "media_capture", "截图 / 录屏"),
    ("item", "screen_mirror", "投屏"),
    ("section", "环境"),
    ("item", "adb_installer", "ADB 环境安装"),
    ("section", "通用工具"),
    ("item", "clipboard", "剪贴板历史"),
    ("item", "hash_tool", "哈希计算"),
    ("item", "encoding_tool", "编码转换"),
    ("item", "timestamp_tool", "时间戳"),
    ("item", "json_tool", "JSON 格式化"),
]


class MainApp(ctk.CTk):
    """主窗口：左侧导航 + 右侧内容。"""

    def __init__(self):
        super().__init__()
        self.title("工具软件")
        self.geometry("1180x760")
        self.minsize(1000, 640)
        self.resizable(True, True)
        if os.path.isfile(_ICON_PATH):
            try:
                self.iconbitmap(_ICON_PATH)
            except Exception:
                pass

        self._adb = find_adb()
        self._serial = None
        self._panels = {}
        self._current_id = None
        self._nav_buttons = {}
        self._child_windows = {}

        self._build_ui()
        self.refresh_devices()
        self.show_panel("device_info")

    def get_adb(self):
        if not self._adb:
            self._adb = find_adb()
        return self._adb

    def get_serial(self):
        return self._serial

    def set_status(self, msg):
        self._status.configure(text=msg or "")

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 顶栏：设备选择
        top = ctk.CTkFrame(self, corner_radius=0, height=52)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(top, text="工具软件", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=(16, 20), pady=10, sticky="w"
        )
        ctk.CTkLabel(top, text="设备").grid(row=0, column=1, padx=(0, 6), pady=10)
        self._device_combo = ctk.CTkComboBox(
            top,
            values=["(未连接)"],
            width=260,
            command=self._on_device_selected,
        )
        self._device_combo.set("(未连接)")
        self._device_combo.grid(row=0, column=2, padx=(0, 8), pady=10, sticky="w")
        ctk.CTkButton(top, text="刷新设备", width=90, command=self.refresh_devices).grid(
            row=0, column=3, padx=(0, 16), pady=10
        )

        # 左侧导航
        side = ctk.CTkFrame(self, width=220, corner_radius=0)
        side.grid(row=1, column=0, sticky="nsw")
        side.grid_propagate(False)

        self._nav_scroll = ctk.CTkScrollableFrame(side, fg_color="transparent", width=200)
        self._nav_scroll.pack(fill="both", expand=True, padx=8, pady=8)

        for entry in _NAV:
            if entry[0] == "section":
                ctk.CTkLabel(
                    self._nav_scroll,
                    text=entry[1],
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="gray60",
                    anchor="w",
                ).pack(fill="x", padx=6, pady=(12, 4))
            else:
                _, item_id, label = entry
                btn = ctk.CTkButton(
                    self._nav_scroll,
                    text=label,
                    anchor="w",
                    height=34,
                    fg_color="transparent",
                    text_color=("gray10", "gray90"),
                    hover_color=("gray80", "gray30"),
                    command=lambda i=item_id: self.show_panel(i),
                )
                btn.pack(fill="x", padx=4, pady=2)
                self._nav_buttons[item_id] = btn

        # 右侧内容
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew", padx=12, pady=12)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._content = ctk.CTkFrame(right, fg_color=("gray95", "gray17"))
        self._content.grid(row=0, column=0, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        # 底栏状态
        self._status = ctk.CTkLabel(self, text="就绪", anchor="w", font=ctk.CTkFont(size=12))
        self._status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))

    def refresh_devices(self):
        adb = self.get_adb()
        if not adb:
            self._device_combo.configure(values=["(未找到 adb)"])
            self._device_combo.set("(未找到 adb)")
            self._serial = None
            self.set_status("未找到 adb，可到「ADB 环境安装」处理")
            return
        serials = list_device_serials(adb)
        if not serials:
            self._device_combo.configure(values=["(未连接)"])
            self._device_combo.set("(未连接)")
            self._serial = None
            self.set_status("未检测到设备")
            return
        self._device_combo.configure(values=serials)
        if self._serial in serials:
            self._device_combo.set(self._serial)
        else:
            self._serial = serials[0]
            self._device_combo.set(self._serial)
        self.set_status(f"已连接 {len(serials)} 台设备")

    def _on_device_selected(self, value):
        if value.startswith("("):
            self._serial = None
        else:
            self._serial = value
            self.set_status(f"当前设备: {value}")

    def show_panel(self, item_id):
        if self._current_id == item_id:
            return

        old = self._panels.get(self._current_id) if self._current_id else None
        if old is not None:
            if hasattr(old, "on_hide"):
                try:
                    old.on_hide()
                except Exception:
                    pass
            old.grid_forget()

        for nid, btn in self._nav_buttons.items():
            if nid == item_id:
                btn.configure(fg_color=("gray75", "gray35"))
            else:
                btn.configure(fg_color="transparent")

        panel = self._panels.get(item_id)
        if panel is None:
            panel = self._create_panel(item_id)
            self._panels[item_id] = panel
            panel.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        else:
            panel.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        self._current_id = item_id
        if hasattr(panel, "on_show"):
            try:
                panel.on_show()
            except Exception:
                pass

    def _create_panel(self, item_id):
        factories = {
            "device_info": DeviceInfoPanel,
            "wireless_adb": WirelessAdbPanel,
            "port_forward": PortForwardPanel,
            "adb_shell": AdbShellPanel,
            "app_manager": AppManagerPanel,
            "media_capture": MediaCapturePanel,
            "clipboard": ClipboardHistoryPanel,
            "hash_tool": HashToolPanel,
            "encoding_tool": EncodingToolPanel,
            "timestamp_tool": TimestampToolPanel,
            "json_tool": JsonToolPanel,
            "file_browser": lambda m, a: LaunchPanel(
                m,
                a,
                "文件浏览器",
                "在独立窗口中浏览设备目录，并支持把设备文件导出到本机。",
                self._open_file_browser,
            ),
            "log_viewer": lambda m, a: LaunchPanel(
                m,
                a,
                "日志输出",
                "在独立窗口中实时显示 Android logcat 日志，支持包名筛选与导出。",
                self._open_log_viewer,
            ),
            "screen_mirror": lambda m, a: LaunchPanel(
                m,
                a,
                "投屏",
                "在独立窗口中进行流畅投屏（scrcpy）或兼容截屏预览。",
                self._open_screen_mirror,
            ),
            "adb_installer": lambda m, a: LaunchPanel(
                m,
                a,
                "ADB 环境安装",
                "安装或配置本机 ADB（platform-tools），便于各调试功能使用。",
                self._open_adb_installer,
            ),
        }
        factory = factories.get(item_id)
        if factory is None:
            frame = ctk.CTkFrame(self._content, fg_color="transparent")
            ctk.CTkLabel(frame, text=f"未实现: {item_id}").pack(padx=20, pady=20)
            return frame
        return factory(self._content, self)

    def _open_unique(self, key, factory):
        win = self._child_windows.get(key)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_force()
                    return
            except Exception:
                pass
        win = factory()
        self._child_windows[key] = win

        def _on_close():
            self._child_windows.pop(key, None)
            try:
                win.destroy()
            except Exception:
                pass

        try:
            win.protocol("WM_DELETE_WINDOW", _on_close)
        except Exception:
            pass

    def _open_log_viewer(self):
        self._open_unique("log", lambda: LogViewerWindow(self))

    def _open_file_browser(self):
        self._open_unique("files", lambda: AdbFileBrowserWindow(self))

    def _open_screen_mirror(self):
        self._open_unique("mirror", lambda: ScreenMirrorWindow(self))

    def _open_adb_installer(self):
        self._open_unique("adb_install", lambda: AdbInstallerWindow(self))


def main():
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        print("程序启动失败，错误信息如下：")
        traceback.print_exc()
        input("按回车键关闭...")
        raise
