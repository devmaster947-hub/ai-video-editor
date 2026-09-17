# Shot Boundary Prompt

Analyze the actual timestamped frames and source metadata. Return JSON only. Detect meaningful shot boundaries without mechanically splitting every transition or camera change.

Keep a continuous complete action together even when the camera angle changes. Keep setup → intervention → payoff together when splitting would remove the operation or result. Split when the person, scene, product state, action goal, or narrative purpose clearly changes. Never invent unseen content.

Return `videos`, each with `source_video`, `source_sha256`, `frame_manifest_hash`, and `shots`. Each shot must contain:

- `shot_id` using `<source_stem>_shot_NNN`
- `start`, `end`, and `duration`
- `boundary_reason`
- `action_complete` and `is_self_contained`
- `similarity_tags`: concise evidence-based product, scene, person, action, and narrative-role tags used only for short-shot merging

Cover the usable source timeline in chronological, non-overlapping intervals. Keep boundaries inside `safe_end` and outside known unsafe black/frozen ranges. Verify every boundary against frames before returning.
