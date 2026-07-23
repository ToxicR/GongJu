# -*- coding: utf-8 -*-
"""共享 ADB 工具：查找 adb、列设备、带序列号执行命令。"""
import os
import subprocess
import sys

from adb_paths import INSTALLED_ADB_EXE, get_bundled_adb_exe

_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
ADB_NAMES = ["adb.exe", "adb"]


def creationflags():
    return _CREATIONFLAGS


def find_adb():
    """查找系统可用的 adb 路径。"""
    for name in ADB_NAMES:
        try:
            r = subprocess.run(
                [name, "version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=_CREATIONFLAGS,
            )
            if r.returncode == 0:
                return name
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
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


def serial_args(serial=None):
    if serial:
        return ["-s", serial]
    return []


def list_device_serials(adb_cmd):
    """返回状态为 device 的序列号列表。"""
    try:
        r = subprocess.run(
            [adb_cmd, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
            creationflags=_CREATIONFLAGS,
        )
        if r.returncode != 0:
            return []
        serials = []
        for line in r.stdout.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
        return serials
    except Exception:
        return []


def list_devices_raw(adb_cmd):
    """返回 (serial, state) 列表，含 unauthorized/offline 等。"""
    try:
        r = subprocess.run(
            [adb_cmd, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
            creationflags=_CREATIONFLAGS,
        )
        if r.returncode != 0:
            return []
        items = []
        for line in r.stdout.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                items.append((parts[0], parts[1]))
        return items
    except Exception:
        return []


def run_adb(adb_cmd, args, serial=None, timeout=30, text=True):
    """
    执行 adb 命令。
    返回 (returncode, stdout, stderr)。
    """
    cmd = [adb_cmd] + serial_args(serial) + list(args)
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=text,
            timeout=timeout,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
            creationflags=_CREATIONFLAGS,
        )
        return r.returncode, r.stdout or (b"" if not text else ""), r.stderr or (b"" if not text else "")
    except subprocess.TimeoutExpired:
        return -1, "" if text else b"", "命令超时"
    except Exception as e:
        return -1, "" if text else b"", str(e)


def shell(adb_cmd, shell_args, serial=None, timeout=30):
    """执行 adb shell ...，shell_args 为字符串或参数列表。"""
    if isinstance(shell_args, str):
        args = ["shell", shell_args]
    else:
        args = ["shell"] + list(shell_args)
    return run_adb(adb_cmd, args, serial=serial, timeout=timeout)
