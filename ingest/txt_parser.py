""".txt parser -- covers the two txt dialects in the corpus:

  기사원고 (news article draft, UTF-8-BOM):
      순서: 10 / 제목: ... / 기자: ... / 기사 ID: ...
      [앵커멘트] ... [기사본문] ... [자막] ... 화면제공/...
  자막 (broadcast subtitle dump, CP949):
      lines; '-' starts a new speaker turn; '(해설)' style speaker labels;
      lone '.' lines separate blocks; NO timecodes.
"""
import re

from .base import BaseParser, RawDoc
from .encoding import normalize_newlines, read_text

_HEADER_RE = re.compile(r"^(순서|제목|기자|기사\s*ID)\s*:\s*(.*)$")
_SECTION_RE = re.compile(r"^\[(앵커멘트|기사본문|자막|리포트)\]\s*$", re.M)


def looks_like_article(text: str) -> bool:
    return bool(_SECTION_RE.search(text)
                or re.search(r"^\s*순서\s*:", text[:400], re.M))


class TxtParser(BaseParser):
    def parse(self, path: str, hint: str | None = None) -> RawDoc:
        text, enc = read_text(path)
        text = normalize_newlines(text)
        if looks_like_article(text):
            raw = self._parse_article(path, text)
        else:
            raw = self._parse_subtitle(path, text)
        raw.encoding = enc
        return raw

    # -- 기사원고 ------------------------------------------------------------
    def _parse_article(self, path: str, text: str) -> RawDoc:
        meta, sections = {}, {}
        current = None
        for line in text.split("\n"):
            stripped = line.strip().lstrip("﻿")
            m = _HEADER_RE.match(stripped)
            if m and current is None:
                key = m.group(1).replace(" ", "")
                meta[{"순서": "order", "제목": "title", "기자": "reporter",
                      "기사ID": "article_id"}.get(key, key)] = m.group(2).strip()
                continue
            m = _SECTION_RE.match(stripped)
            if m:
                current = m.group(1)
                sections.setdefault(current, [])
                continue
            if stripped.startswith("화면제공"):
                meta["footage_credit"] = stripped.split("/", 1)[-1].strip()
                current = None
                continue
            if current is not None and stripped:
                sections[current].append(stripped)

        blocks, sec_names = [], []
        for name in ("앵커멘트", "리포트", "기사본문"):
            if sections.get(name):
                # paragraphs inside a section are wrapped lines; join per blank-line group
                blocks.append(" ".join(sections[name]))
                sec_names.append(name)
        if sections.get("자막"):
            meta["caption"] = " ".join(sections["자막"])
        meta["sections"] = sec_names
        return RawDoc(source_path=path, source_format="txt",
                      doc_type_hint="subtitle_script",
                      text_blocks=blocks, meta=meta)

    # -- 자막 ----------------------------------------------------------------
    def _parse_subtitle(self, path: str, text: str) -> RawDoc:
        """Group wrapped lines into speaker-turn blocks (one block = one utterance)."""
        blocks, meta_turns = [], []
        buf, speaker = [], None

        def flush():
            nonlocal buf, speaker
            joined = " ".join(buf).strip()
            if joined:
                blocks.append(joined)
                meta_turns.append({"speaker": speaker})
            buf, speaker = [], None

        for line in text.split("\n"):
            stripped = line.strip()
            if stripped in ("", "."):          # block separator
                flush()
                continue
            new_turn = stripped.startswith("-")
            if new_turn:
                flush()
                stripped = stripped.lstrip("-").strip()
            m = re.match(r"^\(([^)]{1,10})\)\s*(.*)$", stripped)  # (해설) ...
            if m and (new_turn or not buf):
                speaker = m.group(1)
                stripped = m.group(2)
            if stripped:
                buf.append(stripped)
        flush()
        return RawDoc(source_path=path, source_format="txt",
                      doc_type_hint="subtitle_script",
                      text_blocks=blocks, meta={"turns": meta_turns})
