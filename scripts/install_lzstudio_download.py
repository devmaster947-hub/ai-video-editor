#!/usr/bin/env python3
"""Install the pinned LZStudio CLI for macOS Apple Silicon or Windows x64."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
import tempfile
import urllib.request
from pathlib import Path


RELEASE = "https://github.com/devmaster947-hub/ai-video-editor/releases/download/v4.4.1"
ASSETS = {
    ("Darwin", "arm64"): ("lzstudio-darwin-arm64", "7af107fa2087782763fcfb7528aa8759326c9ca4b8a04c447b42fc55528b0e7d"),
    ("Darwin", "aarch64"): ("lzstudio-darwin-arm64", "7af107fa2087782763fcfb7528aa8759326c9ca4b8a04c447b42fc55528b0e7d"),
    ("Windows", "amd64"): ("lzstudio-windows-x64.exe", "f1c61d3fd5ec0ee5b6a58957494ff21cf220098e4350a4c2f89081f60bf55ab0"),
    ("Windows", "x86_64"): ("lzstudio-windows-x64.exe", "f1c61d3fd5ec0ee5b6a58957494ff21cf220098e4350a4c2f89081f60bf55ab0"),
    ("Windows", "x64"): ("lzstudio-windows-x64.exe", "f1c61d3fd5ec0ee5b6a58957494ff21cf220098e4350a4c2f89081f60bf55ab0"),
}


def destination(system: str) -> Path:
    if system == "Darwin":
        return Path.home() / "Applications" / "LZStudio" / "bin" / "lzstudio"
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return local / "Programs" / "LZStudio" / "bin" / "lzstudio.exe"


def install(target: Path | None = None) -> dict[str, str]:
    system = platform.system()
    machine = platform.machine().lower()
    asset = ASSETS.get((system, machine))
    if asset is None:
        raise RuntimeError("当前安装器仅支持 macOS Apple Silicon 与 Windows x64；其他平台请通过 LZSTUDIO_CLI 指定兼容程序。")
    name, expected = asset
    output = (target or destination(system)).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".lzstudio-", dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
            with urllib.request.urlopen(f"{RELEASE}/{name}", timeout=120) as response:  # nosec - pinned hash below
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
        actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError("LZStudio CLI 下载文件校验失败，未安装。")
        if system != "Windows":
            temporary.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"ok": "true", "path": str(output), "sha256": expected}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.target), ensure_ascii=False))
        return 0
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
