#!/usr/bin/env python3
"""Persist server-created variants while keeping only non-secret structural checks locally."""
from __future__ import annotations

import argparse
from pathlib import Path

from utils import config, dump_json, load_json, normalize_shot, speed_bounds, video_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--response-file", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--library", default="work/shot_library.json")
    ap.add_argument("--narration", default="work/narration_manifest.json")
    ap.add_argument("--output-dir", default="work/variants")
    args = ap.parse_args()

    cfg = config(args.config)
    library = {x["shot_id"]: normalize_shot(x) for x in load_json(args.library, {}).get("shots", [])}
    narration = load_json(args.narration, {})
    segments = {x["script_id"]: x for x in narration.get("script_segments", [])}
    response = load_json(args.response_file, {})
    variants = response.get("variants", [])
    if not variants:
        raise ValueError("server strategy response contains no variants")

    requested = video_count(cfg, sum(1 for x in library.values() if x.get("eligible_for_edit")))
    if len(variants) > requested:
        raise ValueError(f"server returned too many variants; effective videoCount is {requested}")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("variant_*.json"):
        stale.unlink()

    min_speed, max_speed = speed_bounds(cfg)
    for index, variant in enumerate(variants, 1):
        variant = dict(variant)
        variant.setdefault("variant_id", f"variant_{index:02d}")
        seen_shots = set()
        seen_segments = set()
        for clip in variant.get("clips", []):
            shot_id = clip.get("shot_id")
            script_id = clip.get("script_id")
            shot = library.get(shot_id)
            if not shot or not shot.get("eligible_for_edit"):
                raise ValueError(f"{variant['variant_id']}: invalid shot_id {shot_id}")
            if shot_id in seen_shots:
                raise ValueError(f"{variant['variant_id']}: repeated shot_id {shot_id}")
            if script_id not in segments or script_id in seen_segments:
                raise ValueError(f"{variant['variant_id']}: invalid script_id {script_id}")
            target = float(clip.get("target_duration") or 0)
            speed = float(shot.get("duration") or 0) / target if target else 99
            if not min_speed <= speed <= max_speed:
                raise ValueError(f"{variant['variant_id']}: illegal speed for {shot_id}: {speed:.3f}")
            seen_shots.add(shot_id)
            seen_segments.add(script_id)
        if seen_segments != set(segments):
            raise ValueError(f"{variant['variant_id']}: every narration segment must be matched exactly once")
        variant["actual_duration"] = round(sum(float(x.get("target_duration") or 0) for x in variant.get("clips", [])), 3)
        dump_json(out / f"{variant['variant_id']}.json", variant)

    if len(variants) < requested:
        dump_json(
            out / "material_shortage.json",
            {
                "requested": requested,
                "generated": len(variants),
                "reason": response.get("material_shortage_reason", "distinct eligible shots are insufficient"),
                "engineVersion": response.get("engineVersion"),
            },
        )
    print(out)


if __name__ == "__main__":
    main()
