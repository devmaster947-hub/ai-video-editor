#!/usr/bin/env python3
"""Require a working Lingzhi Studio API key immediately before the remote strategy stage."""
from __future__ import annotations

import argparse

from lingzhi_task import require_valid_api_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", help="Optional lzstudio executable path; LZSTUDIO_CLI is also supported")
    args = parser.parse_args()

    try:
        require_valid_api_key(cli_path=args.cli)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None

    print("灵智工坊 API Key 校验通过。")


if __name__ == "__main__":
    main()
