#!/usr/bin/env python3
"""Cross-platform, read-only runtime check for the published WorkBuddy skills."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import sys
from pathlib import Path


PROFILES = {
    "recreate-video-agent": {
        "tools": ("ffmpeg", "ffprobe"),
        "modules": (("PIL", "Pillow"),),
        "needs_lzstudio": True,
    },
    "video-translate-agent": {
        "tools": ("ffmpeg", "ffprobe"),
        "modules": (("pydantic", "pydantic"), ("yaml", "PyYAML"), ("cv2", "opencv-python"), ("numpy", "numpy")),
        "needs_lzstudio": False,
    },
    "ai-video-editor": {
        "tools": ("ffmpeg", "ffprobe"),
        "modules": (),
        "needs_lzstudio": True,
    },
    "product-image-ad": {
        "tools": (),
        "modules": (("PIL", "Pillow"),),
        "needs_lzstudio": True,
    },
    "video-caption-agent": {
        "tools": ("ffmpeg", "ffprobe"),
        "modules": (("cv2", "opencv-python-headless"), ("numpy", "numpy")),
        "needs_lzstudio": True,
    },
}


def find_lzstudio() -> str:
    names = ("lzstudio.exe", "lzstudio") if os.name == "nt" else ("lzstudio",)
    override = os.environ.get("LZSTUDIO_CLI", "").strip()
    candidates = [override, *(shutil.which(name) or "" for name in names)]
    if platform.system() == "Darwin":
        candidates.append(str(Path.home() / "Applications" / "LZStudio" / "bin" / "lzstudio"))
    elif platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        candidates.extend(
            str(path)
            for path in (
                local / "Programs" / "LZStudio" / "bin" / "lzstudio.exe",
                local / "LZStudio" / "bin" / "lzstudio.exe",
            )
        )
    for value in candidates:
        if value and Path(value).expanduser().is_file():
            return str(Path(value).expanduser().resolve())
    return ""


def lzstudio_install_command(system: str) -> str:
    if system == "Windows":
        return r"py -3 scripts\install_lzstudio_download.py"
    return "python3 scripts/install_lzstudio_download.py"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    skill_name = root.name
    profile = PROFILES.get(skill_name)
    if profile is None:
        print(json.dumps({"ok": False, "error": f"未知技能目录：{skill_name}"}, ensure_ascii=False))
        return 2

    system = platform.system()
    supported = system in {"Darwin", "Windows"}
    checks: dict[str, object] = {
        "platform": system,
        "architecture": platform.machine(),
        "python": sys.version.split()[0],
        "skillRoot": str(root),
        "pathIndependent": True,
    }
    missing: list[str] = []
    for tool in profile["tools"]:
        value = shutil.which(str(tool)) or ""
        checks[str(tool)] = value
        if not value:
            missing.append(str(tool))
    for module, package in profile["modules"]:
        available = importlib.util.find_spec(str(module)) is not None
        checks[f"python:{module}"] = available
        if not available:
            missing.append(str(package))
    lzstudio = find_lzstudio()
    checks["lzstudio"] = lzstudio
    if profile["needs_lzstudio"] and not lzstudio:
        missing.append("lzstudio")

    if skill_name == "video-caption-agent":
        whisper = shutil.which("whisper") or ""
        checks["whisper"] = whisper
        if not whisper and importlib.util.find_spec("whisper") is None:
            missing.append("openai-whisper")

    missing_lzstudio = profile["needs_lzstudio"] and not lzstudio
    can_install_lzstudio = (system, platform.machine().lower()) in {
        ("Darwin", "arm64"),
        ("Darwin", "aarch64"),
        ("Windows", "amd64"),
        ("Windows", "x86_64"),
        ("Windows", "x64"),
    }
    next_steps: list[str] = []
    if missing_lzstudio:
        if can_install_lzstudio:
            next_steps.extend(
                [
                    "请先获得用户对下载经 SHA-256 锁定的 LZStudio CLI 的确认。",
                    f"确认后运行：{lzstudio_install_command(system)}",
                    "安装完成后重新运行本预检。",
                ]
            )
        else:
            next_steps.append("当前平台不支持自动安装；请使用 LZSTUDIO_CLI 指向兼容的可执行文件。")
        next_steps.append("不得改用 video-use、media-use、其他 Skill 或本地启发式剪辑流程代替。")
    if any(item != "lzstudio" for item in missing) or not supported:
        next_steps.append("在当前 Skill 目录按 README 的 Windows 或 macOS 安装说明补齐其他缺失项。")
    if missing or not supported:
        next_steps.append("不要移动单个 SKILL.md；必须保留整个 Skill 文件夹。")

    result = {
        "ok": supported and not missing,
        "skill": skill_name,
        "checks": checks,
        "missing": missing,
        "message": "运行环境检查通过。" if supported and not missing else "Skill 已安装，但运行环境尚未准备完整。",
        "fallbackAllowed": False if missing_lzstudio else None,
        "blockingDependency": "lzstudio" if missing_lzstudio else None,
        "install": {
            "supported": can_install_lzstudio,
            "requiresUserConfirmation": True,
            "command": lzstudio_install_command(system) if can_install_lzstudio else "",
        } if missing_lzstudio else None,
        "nextSteps": next_steps,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
