# -*- coding: utf-8 -*-
"""Download and unpack the official Windows scrcpy bundle for packaging."""
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile


SCRCPY_VERSION = "4.0"
SCRCPY_ZIP = f"scrcpy-win64-v{SCRCPY_VERSION}.zip"
SCRCPY_URL = f"https://github.com/Genymobile/scrcpy/releases/download/v{SCRCPY_VERSION}/{SCRCPY_ZIP}"
SCRCPY_SHA256 = "75dbeb5b00e6f64292f26f70900ae55ca397786bdfb0b9bbeb481a0549047457"

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_DIR = os.path.join(ROOT_DIR, "bundled", "scrcpy")


def _log(message):
    print(f"[scrcpy] {message}", flush=True)


def _has_scrcpy():
    return os.path.isfile(os.path.join(TARGET_DIR, "scrcpy.exe"))


def _download(url, dest):
    _log(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response, open(dest, "wb") as f:
        shutil.copyfileobj(response, f)


def _verify_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if digest.lower() != SCRCPY_SHA256.lower():
        raise RuntimeError(f"SHA-256 mismatch: expected {SCRCPY_SHA256}, got {digest}")


def _extract_flat(zip_path, target_dir):
    temp_extract = tempfile.mkdtemp(prefix="scrcpy-extract-")
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(temp_extract)

        entries = [os.path.join(temp_extract, name) for name in os.listdir(temp_extract)]
        roots = [p for p in entries if os.path.isdir(p)]
        source_dir = roots[0] if len(roots) == 1 else temp_extract

        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        shutil.copytree(source_dir, target_dir)
    finally:
        shutil.rmtree(temp_extract, ignore_errors=True)


def main():
    if _has_scrcpy():
        _log(f"already present: {os.path.join(TARGET_DIR, 'scrcpy.exe')}")
        return 0

    if sys.platform != "win32":
        _log("skipped: bundled Windows scrcpy is only needed for Windows packaging")
        return 0

    os.makedirs(os.path.dirname(TARGET_DIR), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scrcpy-download-") as tmp:
        zip_path = os.path.join(tmp, SCRCPY_ZIP)
        _download(SCRCPY_URL, zip_path)
        _verify_sha256(zip_path)
        _extract_flat(zip_path, TARGET_DIR)

    if not _has_scrcpy():
        raise RuntimeError("scrcpy.exe was not found after extraction")
    _log(f"ready: {os.path.join(TARGET_DIR, 'scrcpy.exe')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
