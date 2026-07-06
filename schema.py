"""P0 -- canonical schemas shared by every UDA stage.

Dataclass-based (stdlib only) so workers/tests run without extra installs.
``CanonicalDocument`` is the ONLY contract between the ingest layer and the
analyze layer: new file formats only add parsers, new models only add
analyzers -- neither side touches the other.
"""
from dataclasses import dataclass, field, asdict

# Document types found in the sample corpus (비정형 수집 데이터 목록):
#   cuesheet        큐시트        (xlsx/pdf/hwp, carries timecodes)
#   narration       나레이션원고/대본 (pdf/hwp)
#   schedule        편성표        (no samples yet -- format TBD)
#   subtitle_script 자막/기사원고  (txt; subtitles have NO timecodes)
#   clip_meta       영상 메타      (.mp4.xml clipInfo)
DOC_TYPES = ("cuesheet", "narration", "schedule", "subtitle_script", "clip_meta")


@dataclass
class Segment:
    """One minimal unit of a document (cuesheet row, speaker turn, paragraph)."""
    seg_id: str
    text: str
    order: int | None = None
    start_time_seconds: float | None = None   # None until aligned (subtitles)
    end_time_seconds: float | None = None
    speaker: str | None = None                # "앵커", "해설", reporter name, ...
    kind: str | None = None                   # cuesheet 구분(S/R) + 형식(eVCR/CG) etc.
    raw: dict = field(default_factory=dict)   # original fields, for traceability

    def to_dict(self):
        return asdict(self)


@dataclass
class CanonicalDocument:
    """Normalized document -- the contract between ingest and analyze."""
    doc_id: str
    doc_type: str                             # one of DOC_TYPES
    source_format: str                        # pdf/hwp/xlsx/txt/xml
    source_path: str = ""
    program: str | None = None                # 뉴스데스크 / 프라임인터뷰 / ...
    air_date: str | None = None
    clip_id: str | None = None                # joins with .mp4.xml CLIPID
    program_meta: dict = field(default_factory=dict)
    segments: list = field(default_factory=list)   # list[Segment]

    @property
    def full_text(self) -> str:
        return "\n".join(s.text for s in self.segments if s.text)

    def to_dict(self):
        return asdict(self)


@dataclass
class TimeCodedSummary:
    """Extractive summary of one time window (original sentences, no generation)."""
    start_time_seconds: float | None
    end_time_seconds: float | None
    summary: str
    source_seg_ids: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    speaker: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass
class UDResult:
    """Final UD output handed to the TA (time-series alignment) stage."""
    doc_id: str
    doc_type: str
    cues: list = field(default_factory=list)                 # list[Segment], time-coded
    time_coded_summaries: list = field(default_factory=list)  # list[TimeCodedSummary]
    keywords: list = field(default_factory=list)
    program_meta: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)
