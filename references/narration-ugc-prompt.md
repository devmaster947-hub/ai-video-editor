# UGC Narration Prompt

Use this prompt for the two mutually exclusive narration inputs: `narrationMode: audio` and `narrationMode: script`. Read `shot_library.json`, product facts from config, and exactly one authoritative narration source: the Whisper transcript of the supplied audio, or `input/voiceover_script.txt`. Return JSON only.

Preserve the authoritative narration's meaning, wording order, claims, and CTA. Do not invent, remove, soften, strengthen, or reorder selling points. You may normalize obvious transcription punctuation and homophone errors in `audio` mode, or create pronunciation-only aliases in `spoken_text` for `script` mode. If the footage cannot support a claim, report the conflict and stop instead of silently rewriting the narration.

## Mode rules

- `audio`: Use the Whisper transcript of the supplied voiceover audio as the source. Keep every spoken idea in its original order. Segment it for matching, but do not rewrite it and do not create TTS. Set `source_transcript` to the complete cleaned transcript. `text` must remain close enough to the transcript for deterministic similarity validation.
- `script`: Use the user's supplied script as the source. Keep the wording and order unless the user explicitly authorizes rewriting. `text` is the caption wording; `spoken_text` may differ only for pronunciation, number reading, abbreviations, and natural pauses. TTS uses the user-selected `tts_voice`; when it is empty, the runtime uses the configured default voice.

Keep each semantic segment complete and visually atomic: describe exactly one visible garment area, one visible action, and one visible result. Never combine alternatives such as side waist, chest, and sleeve in one segment. Split them into separate segments only when distinct supporting shots exist. A segment may contain several short sentences and should normally last 3–6 seconds. Set `pause_after_ms` to 120–280; use 120–200 for a normal transition and 220–280 only for a change of thought.

Write `text` for on-screen captions and `spoken_text` for pronunciation. Keep their meaning identical. Use natural phonetic Chinese in `spoken_text` for mixed-script terms when necessary (for example, caption `T恤` may use spoken `踢恤`) so a Latin letter never creates an internal pause. Do not insert pronunciation punctuation or spaces inside a lexical item.

For every segment in both modes, copy one exact `visual_requirements` value from the cited shots' `visual_facts`. It must contain exactly one value in each of `garment_area`, `action`, and `result`; every cited evidence shot must cover all three values. Every segment must cite at least one existing `shot_id`. If no shot fully covers a segment, return a conflict instead of changing the narration.

Return:

```json
{
  "narrationMode": "script",
  "source_transcript": "Required only in audio mode; complete cleaned transcript",
  "optimized_script": "The supplied narration, segmented without changing its meaning or order",
  "segments": [
    {
      "segment_id": "segment_001",
      "text": "Authoritative narration segment for captions.",
      "spoken_text": "The same wording, changed only when pronunciation requires it.",
      "pause_after_ms": 180,
      "visual_requirements": {"garment_area": ["waist"], "action": ["fasten"], "result": ["tightened"]},
      "evidence_shot_ids": ["existing_shot_id", "alternate_existing_shot_id"]
    }
  ]
}
```

`spoken_text`, `visual_requirements`, and `evidence_shot_ids` are required for every segment in both modes. Include only alternatives that cover the entire visual requirement, not broadly related shots. Use only immutable existing IDs; never return source paths or time ranges. For `audio`, the concatenated segment `text` must closely match `source_transcript`; for `script`, it must preserve the supplied script.
