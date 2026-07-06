"""udav1 -- Unstructured Data Analysis (broadcasting/media, LLM-free).

Layer 1 (ingest)   : format parsers (txt/xlsx/xml/pdf/hwp) -> RawDoc
Layer 1.5 (normalize): RawDoc -> CanonicalDocument (the single contract)
Layer 2 (analyze)  : sentence split / subtitle<->ASR time alignment /
                     time windowing / extractive summarization

Entry point: ``udav1.pipeline.analyze_path`` or ``python -m udav1 <file>``.
"""

__version__ = "0.1.0"

from .pipeline import analyze_path, analyze  # noqa: F401
