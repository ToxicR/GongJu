# -*- coding: utf-8 -*-
"""
Windows 工具软件 - 主入口
启动后显示功能选择菜单，支持日志输出等模块。
"""
import os
import customtkinter as ctk
from log_viewer import LogViewerWindow
from adb_file_browser import AdbFileBrowserWindow
from screen_mirror import ScreenMirrorWindow
from adb_installer import AdbInstallerWindow

_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")

# 主题与外观
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MainApp(ctk.CTk):
    """主窗口：功能选择"""

    def __init__(self):
        super().__init__()
        self.title("工具软件")
        self.geometry("480x400")
        self.resizable(True, True)
        if os.path.isfile(_ICON_PATH):
            try:
                self.iconbitmap(_ICON_PATH)
            except Exception:
                pass
        self._build_ui()

    def _build_ui(self):
        # 标题
        title = ctk.CTkLabel(
            self,
            text="请选择要使用的功能",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title.pack(pady=(32, 24))

        # 功能按钮容器
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=40, pady=20)

        # 1. 日志输出功能
        btn_log = ctk.CTkButton(
            frame,
            text="1. 日志输出功能",
            font=ctk.CTkFont(size=16),
            height=48,
            width=320,
            command=self._open_log_viewer,
        )
        btn_log.pack(pady=12)

        # 2. ADB 文件浏览器
        btn_files = ctk.CTkButton(
            frame,
            text="2. ADB 文件浏览器",
            font=ctk.CTkFont(size=16),
            height=48,
            width=320,
            command=self._open_file_browser,
        )
        btn_files.pack(pady=12)

        # 3. 投屏
        btn_mirror = ctk.CTkButton(
            frame,
            text="3. 投屏",
            font=ctk.CTkFont(size=16),
            height=48,
            width=320,
            command=self._open_screen_mirror,
        )
        btn_mirror.pack(pady=12)

        # 4. ADB 环境安装
        btn_adb_install = ctk.CTkButton(
            frame,
            text="4. ADB 环境安装",
            font=ctk.CTkFont(size=16),
            height=48,
            width=320,
            command=self._open_adb_installer,
        )
        btn_adb_install.pack(pady=12)

        # 预留更多功能入口
        hint = ctk.CTkLabel(
            frame,
            text="更多功能敬请期待",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        hint.pack(pady=8)

    def _open_log_viewer(self):
        """打开 Android 日志输出窗口"""
        win = LogViewerWindow(self)
        win.grab_set()
        self.wait_window(win)

    def _open_file_browser(self):
        """打开 ADB 文件浏览器窗口"""
        win = AdbFileBrowserWindow(self)
        win.grab_set()
        self.wait_window(win)

    def _open_screen_mirror(self):
        """打开投屏窗口"""
        win = ScreenMirrorWindow(self)
        win.grab_set()
        self.wait_window(win)

    def _open_adb_installer(self):
        """打开 ADB 环境安装窗口并自动安装配置"""
        win = AdbInstallerWindow(self)
        win.grab_set()
        self.wait_window(win)


def main():
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("程序启动失败，错误信息如下：")
        traceback.print_exc()
        input("按回车键关闭...")
        raise
