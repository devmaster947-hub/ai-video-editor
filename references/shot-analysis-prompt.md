# Shot Analysis Prompt

Analyze only the independent MP4 clips listed in `final_shot_manifest.json`. Return JSON only with `shots`; return exactly one record for every selectable `shot_id` and no unknown IDs. Do not return source-video time ranges.

Each record must contain `shot_id`, `visual_summary`, `people`, `action`, `product`, `product_state`, `scene`, `story_roles`, `action_complete`, `is_self_contained`, `burned_caption`, `tags`, and `eligible_for_edit`.

Describe only visible evidence. Use `无法确认` when the product or identity is uncertain. Mark incomplete, unsafe, misleading, or unusable content ineligible. A merged clip may contain several related angles; describe the combined visual meaning and verify that its sequence remains coherent.
