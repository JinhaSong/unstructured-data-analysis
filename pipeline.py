"""Pipeline orchestrator: file -> RawDoc -> CanonicalDocument -> UDResult.

    parse (ingest) -> normalize -> [align to ASR] -> window -> summarize
"""
from . import configs, ingest, normalize
from .analyze.align import align_segments_to_asr
from .analyze.summarize import extract_keywords, summarize_window
from .analyze.window import build_windows
from .schema import UDResult


def analyze_path(path: str, doc_type: str | None = None,
                 asr_segments: list | None = None) -> UDResult:
    """Analyze one unstructured file.

    ``asr_segments``: faster-whisper style [{start_time_seconds,
    end_time_seconds, text}, ...] -- when given and the document has no
    timecodes of its own, ASR time is grafted onto the segments (P2).
    """
    raw = ingest.parse(path, doc_type)
    doc = normalize.to_canonical(raw)

    needs_time = any(s.start_time_seconds is None for s in doc.segments)
    if asr_segments and needs_time:
        align_segments_to_asr(doc.segments, asr_segments)

    cfg = configs.for_doc_type(doc.doc_type)
    windows = build_windows(
        doc, strategy=cfg["window"],
        gap_seconds=cfg.get("gap_seconds", 2.0),
        window_seconds=cfg.get("window_seconds", 30.0))
    summaries = [summarize_window(w, max_sentences=cfg["max_sentences"])
                 for w in windows]

    return UDResult(
        doc_id=doc.doc_id, doc_type=doc.doc_type,
        cues=doc.segments, time_coded_summaries=summaries,
        keywords=extract_keywords(doc.full_text, topn=10),
        program_meta=doc.program_meta)


def analyze(unstructured_input: dict) -> dict:
    """Dict-based entry point for the parent pipeline's UD celery task.

    {"files": [{"path": ..., "doc_type": ...?}, ...] | "path": ...,
     "asr_segments": [...]}   ->   {doc_id: UDResult-dict}
    """
    unstructured_input = unstructured_input or {}
    files = unstructured_input.get("files")
    if not files and unstructured_input.get("path"):
        files = [{"path": unstructured_input["path"],
                  "doc_type": unstructured_input.get("doc_type")}]
    asr = unstructured_input.get("asr_segments")

    results = {}
    for spec in files or []:
        result = analyze_path(spec["path"], spec.get("doc_type"), asr)
        results[result.doc_id] = result.to_dict()
    return results
