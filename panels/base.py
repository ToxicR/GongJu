# -*- coding: utf-8 -*-
"""面板基类与公共小部件。"""
import customtkinter as ctk


class BasePanel(ctk.CTkFrame):
    """右侧内容面板基类。"""

    title = "面板"

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._build()

    def _build(self):
        raise NotImplementedError

    @property
    def adb(self):
        return self.app.get_adb()

    @property
    def serial(self):
        return self.app.get_serial()

    def on_show(self):
        """面板被切换显示时调用。"""
        pass

    def set_status(self, msg):
        self.app.set_status(msg)


class LaunchPanel(BasePanel):
    """打开独立窗口的引导面板。"""

    def __init__(self, master, app, title, description, open_callback):
        self._panel_title = title
        self._description = description
        self._open_callback = open_callback
        super().__init__(master, app)

    def _build(self):
        ctk.CTkLabel(
            self,
            text=self._panel_title,
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(8, 12))
        ctk.CTkLabel(
            self,
            text=self._description,
            font=ctk.CTkFont(size=14),
            text_color="gray70",
            anchor="w",
            justify="left",
            wraplength=700,
        ).pack(fill="x", padx=8, pady=(0, 20))
        ctk.CTkButton(
            self,
            text="打开窗口",
            width=160,
            height=40,
            font=ctk.CTkFont(size=15),
            command=self._open_callback,
        ).pack(anchor="w", padx=8)
