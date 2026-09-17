#!/usr/bin/env python3
"""Call the server-side edit strategy engine through Lingzhi Studio task submit/fetch."""
from __future__ import annotations

import argparse
from pathlib import Path

from lingzhi_task import require_valid_api_key, submit_and_wait
from utils import config, dump_json, load_json, normalize_shot, video_count


def compact_shot(shot):
    row = normalize_shot(shot)
    return {
        "shot_id": row.get("shot_id"),
        "duration": row.get("duration", row.get("time", {}).get("duration", 0)),
        "eligible_for_edit": bool(row.get("eligible_for_edit", False)),
        "usable_position": row.get("usable_position", []),
        "person": {"person_id": row.get("person", {}).get("person_id", "")},
        "product": {
            "visible": bool(row.get("product", {}).get("visible", False)),
            "name": row.get("product", {}).get("name", ""),
            "interaction": row.get("product", {}).get("interaction", "none"),
            "state": row.get("product", {}).get("state", "unknown"),
        },
        "continuity": row.get("continuity", {}),
        "tags": row.get("tags", []),
        "visual_facts": row.get("visual_facts", {}),
        "action_complete": bool(row.get("action_complete", False)),
        "is_self_contained": bool(row.get("is_self_contained", False)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--library", default="work/shot_library.json")
    ap.add_argument("--narration", default="work/narration_manifest.json")
    ap.add_argument("--generation-context", default="work/generation_context.json")
    ap.add_argument("--output", default="work/strategy_response.json")
    args = ap.parse_args()

    cfg = config(args.config)
    try:
        require_valid_api_key(cli_path=str(cfg.get("lzstudio_cli_path") or "") or None)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    library = load_json(args.library, {}) or {}
    narration = load_json(args.narration, {}) or {}
    context = load_json(args.generation_context, {}) or {}
    segments = narration.get("script_segments", [])
    evidence_ids = {str(sid) for seg in segments for sid in seg.get("evidence_shot_ids", [])}
    source_shots = [x for x in library.get("shots", []) if x.get("shot_id") in evidence_ids]
    compact_shots = [compact_shot(x) for x in source_shots]
    eligible_total = sum(1 for x in library.get("shots", []) if x.get("eligible_for_edit"))

    payload = {
        "schemaVersion": 1,
        "operation": "plan_edit",
        "client": "ai-video-editor-v4.3",
        "config": {
            "videoCount": video_count(cfg, eligible_total),
            "min_speed_ratio": float(cfg.get("min_speed_ratio", 0.92)),
            "max_speed_ratio": min(1.3, float(cfg.get("max_speed_ratio", 1.3))),
        },
        "shotLibrary": {"shots": compact_shots},
        "narration": {
            "duration": narration.get("duration", 0),
            "script_segments": [
                {
                    "script_id": seg.get("script_id"),
                    "duration": seg.get("duration", 0),
                    "text": seg.get("text", ""),
                    "visual_requirements": seg.get("visual_requirements", {}),
                    "evidence_shot_ids": seg.get("evidence_shot_ids", []),
                }
                for seg in segments
            ],
        },
        "generationContext": {
            "effectiveVideoCount": context.get("effectiveVideoCount", context.get("effective_videoCount")),
            "eligibleShotCount": context.get("eligible_shot_count", eligible_total),
        },
    }

    workflow_id = str(cfg.get("strategy_workflow_id") or "VideoEditingPolicyV1")
    result = submit_and_wait(
        payload,
        workflow_id=workflow_id,
        cli_path=str(cfg.get("lzstudio_cli_path") or "") or None,
        timeout_seconds=float(cfg.get("strategy_timeout_seconds", 180)),
        poll_seconds=float(cfg.get("strategy_poll_seconds", 1.5)),
    )
    if result.get("operation") not in (None, "plan_edit"):
        raise RuntimeError(f"unexpected strategy operation: {result.get('operation')}")
    if not result.get("variants"):
        raise RuntimeError(result.get("error") or "server strategy returned no variants")
    dump_json(args.output, result)
    print(args.output)


if __name__ == "__main__":
    main()
