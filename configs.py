"""Per-doc_type pipeline configuration (plain dicts; no YAML dep)."""

# doc_type -> windowing strategy + params + summary size
PIPELINES = {
    "cuesheet":        {"window": "item",         "max_sentences": 1},
    "narration":       {"window": "speaker_turn", "max_sentences": 2},
    "schedule":        {"window": "item",         "max_sentences": 1},
    "subtitle_script": {"window": "gap", "gap_seconds": 2.0, "max_sentences": 2},
    "clip_meta":       {"window": "item",         "max_sentences": 1},
}

DEFAULT = {"window": "fixed", "window_seconds": 30.0, "max_sentences": 2}


def for_doc_type(doc_type: str) -> dict:
    cfg = dict(DEFAULT)
    cfg.update(PIPELINES.get(doc_type, {}))
    return cfg
