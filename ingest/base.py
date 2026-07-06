"""Parser-side raw representation. Type knowledge lives in normalize/, not here."""
from dataclasses import dataclass, field


@dataclass
class RawDoc:
    """Low-level, type-agnostic parse result of one file."""
    source_path: str
    source_format: str                        # txt/xlsx/xml/pdf/hwp
    encoding: str | None = None
    doc_type_hint: str | None = None          # from path keywords / caller
    text_blocks: list = field(default_factory=list)   # list[str] (paragraph-ish)
    tables: list = field(default_factory=list)        # list[table]; table = list[row]; row = list[str]
    meta: dict = field(default_factory=dict)          # KV pairs (clipInfo, header fields)


class BaseParser:
    """Interface: parse(path, hint) -> RawDoc."""

    def parse(self, path: str, hint: str | None = None) -> RawDoc:  # pragma: no cover
        raise NotImplementedError
