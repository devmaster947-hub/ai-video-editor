#!/usr/bin/env python3
"""Submit/fetch Lingzhi Studio arbitrary workflow tasks via the bundled CLI.

The CLI invocation follows the documented shape:
  lzstudio task submit --api-key ... --workflow-id ... --input '{...}'
  lzstudio task fetch  --api-key ... --id ...

Large JSON payloads are passed through a System.CommandLine response file so
Windows command-line length limits do not expose or truncate the payload.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_KEY_GUIDANCE = "请获取灵智工坊API Key：[https://www.lingzhiai.com.cn/](https://www.lingzhiai.com.cn/)"
API_KEY_ENV_NAMES = ("LZSTUDIO_API_KEY", "RECREATE_VIDEO_API_KEY", "LINGZHI_API_KEY")


class CredentialNotFoundError(RuntimeError):
    """No non-empty credential exists in any supported source."""


class CredentialConfigError(RuntimeError):
    """A known credential file exists but cannot be parsed safely."""


def credential_config_paths() -> list[Path]:
    """Return a small allowlist of compatible local credential stores."""
    candidates: list[Path] = []
    override = os.getenv("LZSTUDIO_CONFIG", "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    home = Path.home()
    candidates.extend(
        [
            home / ".recreate-video" / "config.json",
            home / ".ugc-product-video" / "config.json",
            home / ".product-image-ad" / "config.json",
        ]
    )
    result: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        marker = str(path.resolve(strict=False))
        if marker not in seen:
            result.append(path)
            seen.add(marker)
    return result


def _read_config_key(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CredentialConfigError(f"无法读取灵智工坊 Key 配置：{path}") from exc
    if not isinstance(data, dict):
        raise CredentialConfigError(f"灵智工坊 Key 配置必须是 JSON 对象：{path}")
    value = data.get("apiKey", "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CredentialConfigError(f"灵智工坊 Key 配置中 apiKey 必须是字符串：{path}")
    return value.strip()


def _json_loads_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def find_cli(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    for raw in (explicit, os.getenv("LZSTUDIO_CLI")):
        if raw:
            candidates.append(Path(raw).expanduser())

    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        candidates.append(ROOT / "tools/lzstudio/darwin-arm64/lzstudio")
    elif system == "windows" and machine in {"amd64", "x86_64"}:
        candidates.append(ROOT / "tools/lzstudio/windows-x64/lzstudio.exe")

    found = shutil.which("lzstudio") or shutil.which("lzstudio.exe")
    if found:
        candidates.append(Path(found))

    for candidate in candidates:
        if candidate.is_file():
            if system != "windows":
                try:
                    candidate.chmod(candidate.stat().st_mode | stat.S_IXUSR)
                except OSError:
                    pass
            return candidate.resolve()

    raise RuntimeError(
        "Lingzhi Studio CLI not found. Set LZSTUDIO_CLI or use the bundled "
        "macOS arm64 / Windows x64 binary."
    )


def resolve_api_key(
    explicit: str | None = None,
    *,
    config_paths: list[Path] | None = None,
) -> tuple[str, str]:
    """Resolve a key and its non-secret source label in deterministic order."""
    explicit_value = str(explicit or "").strip()
    if explicit_value:
        return explicit_value, "explicit"

    for name in API_KEY_ENV_NAMES:
        value = os.getenv(name, "").strip()
        if value:
            return value, f"env:{name}"

    errors: list[CredentialConfigError] = []
    for path in config_paths if config_paths is not None else credential_config_paths():
        try:
            value = _read_config_key(Path(path))
        except CredentialConfigError as exc:
            errors.append(exc)
            continue
        if value:
            return value, f"config:{path}"

    if errors:
        raise errors[0]
    raise CredentialNotFoundError("Missing Lingzhi Studio API key")


def api_key(explicit: str | None = None, *, config_paths: list[Path] | None = None) -> str:
    return resolve_api_key(explicit, config_paths=config_paths)[0]


def _redact(text: str, *secrets: str) -> str:
    result = str(text)
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[REDACTED]")
    return result


def validate_api_key(
    *,
    cli_path: str | None = None,
    key: str | None = None,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    """Validate credentials through a read-only account query."""
    # Check for the credential before resolving runtimes/tools so a missing
    # Python/CLI installation is never confused with a missing API key.
    secret = api_key(key)
    cli = find_cli(cli_path)
    return _run_cli(
        cli,
        ["account", "--credits", "--api-key", secret],
        timeout=max(5.0, float(timeout_seconds)),
    )


def require_valid_api_key(
    *,
    cli_path: str | None = None,
    key: str | None = None,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    """Return account data and distinguish credential failures from runtime failures."""
    try:
        secret = api_key(key)
    except CredentialNotFoundError as exc:
        raise RuntimeError(API_KEY_GUIDANCE) from exc
    except CredentialConfigError as exc:
        raise RuntimeError(str(exc)) from exc

    try:
        cli = find_cli(cli_path)
        return _run_cli(
            cli,
            ["account", "--credits", "--api-key", secret],
            timeout=max(5.0, float(timeout_seconds)),
        )
    except Exception as exc:
        message = _redact(str(exc).strip(), secret)
        normalized = message.lower()
        credential_markers = (
            "invalid api key",
            "api key is invalid",
            "unauthorized",
            "forbidden",
            "authentication failed",
            "status 401",
            "status 403",
            "http 401",
            "http 403",
        )
        if any(marker in normalized for marker in credential_markers):
            raise RuntimeError(API_KEY_GUIDANCE) from exc
        raise RuntimeError(f"灵智工坊 API Key 校验未完成：{message}") from exc


def _rsp_quote(arg: str) -> str:
    # System.CommandLine response files understand ordinary double-quoted
    # command-line tokens. JSON is compacted before reaching this function.
    escaped = str(arg).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _run_cli(cli: Path, args: list[str], *, timeout: float = 120) -> dict[str, Any]:
    # Windows needs response-file expansion to avoid its ~32K command-line
    # limit. The current macOS CLI build misparses escaped JSON in response
    # files, while macOS has a substantially larger argv limit, so pass the
    # compact payload directly there.
    secrets = [str(args[i + 1]) for i, arg in enumerate(args[:-1]) if arg == "--api-key"]
    if platform.system().lower() != "windows":
        proc = subprocess.run(
            [str(cli), *args],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode:
            message = _redact(
                (proc.stderr or proc.stdout or "Lingzhi Studio CLI failed").strip(),
                *secrets,
            )
            raise RuntimeError(message)
        text = (proc.stdout or "").strip()
        if not text:
            raise RuntimeError("Lingzhi Studio CLI returned an empty response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            safe_text = _redact(text[:500], *secrets)
            raise RuntimeError(f"Lingzhi Studio CLI returned non-JSON output: {safe_text}") from exc

    fd, rsp_name = tempfile.mkstemp(prefix="lzstudio_", suffix=".rsp")
    rsp = Path(rsp_name)
    try:
        os.close(fd)
        try:
            os.chmod(rsp, 0o600)
        except OSError:
            pass
        rsp.write_text("\n".join(_rsp_quote(x) for x in args) + "\n", encoding="utf-8")
        proc = subprocess.run(
            [str(cli), "@" + str(rsp)],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    finally:
        try:
            rsp.unlink()
        except FileNotFoundError:
            pass

    if proc.returncode:
        message = _redact(
            (proc.stderr or proc.stdout or "Lingzhi Studio CLI failed").strip(),
            *secrets,
        )
        raise RuntimeError(message)

    text = (proc.stdout or "").strip()
    if not text:
        raise RuntimeError("Lingzhi Studio CLI returned an empty response")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        safe_text = _redact(text[:500], *secrets)
        raise RuntimeError(f"Lingzhi Studio CLI returned non-JSON output: {safe_text}") from exc


def _unwrap_output(value: Any) -> Any:
    value = _json_loads_maybe(value)
    # Keep real engine payloads intact. Only peel generic transport wrappers.
    for _ in range(4):
        if not isinstance(value, dict):
            break
        if any(k in value for k in ("variants", "rankings", "engineVersion", "operation")):
            break
        for key in ("body", "data", "result", "output"):
            if key in value and len(value) <= 3:
                value = _json_loads_maybe(value[key])
                break
        else:
            break
    return value


def submit_and_wait(
    payload: dict[str, Any],
    *,
    workflow_id: str,
    cli_path: str | None = None,
    key: str | None = None,
    timeout_seconds: float = 180,
    poll_seconds: float = 1.5,
) -> dict[str, Any]:
    cli = find_cli(cli_path)
    secret = api_key(key)
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    created = _run_cli(
        cli,
        ["task", "submit", "--api-key", secret, "--workflow-id", workflow_id, "--input", compact],
        timeout=min(120, timeout_seconds),
    )
    task_id = str(created.get("id") or "").strip()
    if not task_id:
        raise RuntimeError(f"Lingzhi Studio task submit returned no id: {created}")

    deadline = time.monotonic() + max(5.0, float(timeout_seconds))
    last: dict[str, Any] = created
    while time.monotonic() < deadline:
        fetched = _run_cli(
            cli,
            ["task", "fetch", "--api-key", secret, "--id", task_id],
            timeout=min(120, timeout_seconds),
        )
        last = fetched
        status = str(fetched.get("status") or "").strip().lower()
        if status in {"succeeded", "success", "completed", "complete"}:
            result = _unwrap_output(fetched.get("output"))
            if not isinstance(result, dict):
                raise RuntimeError(f"Workflow output is not a JSON object: {result!r}")
            return result
        if status in {"failed", "error", "cancelled", "canceled", "timedout", "timed_out"}:
            raise RuntimeError(str(fetched.get("errorMessage") or fetched.get("error") or fetched))
        time.sleep(max(0.2, float(poll_seconds)))

    raise TimeoutError(f"Lingzhi Studio task {task_id} timed out; last status={last.get('status')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-id", required=True)
    ap.add_argument("--input-file", required=True)
    ap.add_argument("--output-file", required=True)
    ap.add_argument("--cli")
    ap.add_argument("--api-key")
    ap.add_argument("--timeout-seconds", type=float, default=180)
    ap.add_argument("--poll-seconds", type=float, default=1.5)
    args = ap.parse_args()

    payload = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    result = submit_and_wait(
        payload,
        workflow_id=args.workflow_id,
        cli_path=args.cli,
        key=args.api_key,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    out = Path(args.output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
