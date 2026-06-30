# -*- coding: utf-8 -*-
"""ADB 路径：内置资料目录与安装目录。"""
import os
import sys

_SDK_PARENT_DIR = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk")
INSTALL_DIR = os.path.join(_SDK_PARENT_DIR, "platform-tools")
INSTALLED_ADB_EXE = os.path.join(INSTALL_DIR, "adb.exe")


def get_app_base_dir():
    """开发时为项目目录，PyInstaller 打包后为临时解压目录。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_bundled_platform_tools_dir():
    return os.path.join(get_app_base_dir(), "bundled", "platform-tools")


def get_bundled_adb_exe():
    path = os.path.join(get_bundled_platform_tools_dir(), "adb.exe")
    return path if os.path.isfile(path) else None
