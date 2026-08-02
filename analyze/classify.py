"""udav2 P2 — 문서 유형 분류.

규칙 1차(JSON doc_type 필드·파일명·구조 힌트 — ingest가 이미 판별) / 모호
케이스만 KoELECTRA 분류 헤드로 넘기는 구조. 분류 헤드는 M2에서 문서 수백 건
파인튜닝 후 장착 — 현재는 규칙 결과를 그대로 신뢰하고 method만 보고한다.
"""
from ..schema import DOC_TYPES_V2


def classify(doc) -> tuple[str, str]:
    """CanonicalDocument -> (doc_type, method)."""
    if doc.doc_type in DOC_TYPES_V2 and doc.doc_type != "other":
        return doc.doc_type, "rule"
    # TODO(M2): KoELECTRA-base-v3 분류 헤드 (Apache-2.0) — full_text 입력
    return doc.doc_type or "other", "rule-fallback"
