"""P2 -- graft ASR timecodes onto un-timed subtitle segments.

Subtitles in this corpus are clean text WITHOUT timecodes; the MMCA ASR
output (faster-whisper) is noisy text WITH timecodes. Aligning the two
character-wise transfers time onto the subtitle -- the core added value
of the UD stage for the TA aligner.

Method (deterministic, stdlib difflib; rapidfuzz optional for scoring):
  1. normalize both sides (drop spaces/punct), keeping per-char time for ASR
     (linear interpolation inside each ASR segment)
  2. one global SequenceMatcher over the two normalized strings
  3. each subtitle segment's matched char span -> [min_time, max_time]
  4. unmatched segments get interpolated between timed neighbours
"""
from difflib import SequenceMatcher

from ..utils import norm_for_match

_MIN_MATCH_RATIO = 0.3   # a segment must match >=30% of its chars to be "timed"


def _asr_char_times(asr_segments):
    """Concatenate normalized ASR text; per-char (start,end) times."""
    chars, times = [], []
    for seg in asr_segments:
        text = norm_for_match(seg.get("text", ""))
        if not text:
            continue
        start = float(seg.get("start_time_seconds", 0.0))
        end = float(seg.get("end_time_seconds", start))
        n = len(text)
        for i, ch in enumerate(text):
            chars.append(ch)
            t0 = start + (end - start) * i / n
            t1 = start + (end - start) * (i + 1) / n
            times.append((t0, t1))
    return "".join(chars), times


def align_segments_to_asr(segments, asr_segments):
    """Fill start/end_time_seconds of ``segments`` in place; returns segments.

    ``asr_segments``: [{start_time_seconds, end_time_seconds, text}, ...]
    (faster-whisper transcript format used across this project).
    """
    if not segments or not asr_segments:
        return segments

    ref_text, ref_times = _asr_char_times(asr_segments)
    if not ref_text:
        return segments

    # subtitle side: concatenated normalized text + per-segment spans
    sub_parts, spans = [], []
    pos = 0
    for seg in segments:
        norm = norm_for_match(seg.text)
        spans.append((pos, pos + len(norm)))
        sub_parts.append(norm)
        pos += len(norm)
    sub_text = "".join(sub_parts)

    sm = SequenceMatcher(None, sub_text, ref_text, autojunk=False)
    blocks = sm.get_matching_blocks()

    for seg, (s0, s1) in zip(segments, spans):
        if s1 == s0:
            continue
        lo, hi, matched = None, None, 0
        for a, b, size in blocks:
            ov0, ov1 = max(a, s0), min(a + size, s1)
            if ov0 >= ov1:
                continue
            matched += ov1 - ov0
            r0, r1 = b + (ov0 - a), b + (ov1 - a) - 1
            lo = ref_times[r0][0] if lo is None else min(lo, ref_times[r0][0])
            hi = ref_times[r1][1] if hi is None else max(hi, ref_times[r1][1])
        if matched >= (s1 - s0) * _MIN_MATCH_RATIO and lo is not None:
            seg.start_time_seconds = round(lo, 3)
            seg.end_time_seconds = round(hi, 3)

    _interpolate_gaps(segments)
    return segments


def _interpolate_gaps(segments):
    """Give unmatched segments times interpolated between timed neighbours."""
    timed = [i for i, s in enumerate(segments) if s.start_time_seconds is not None]
    if not timed:
        return
    for i, seg in enumerate(segments):
        if seg.start_time_seconds is not None:
            continue
        prev = max((j for j in timed if j < i), default=None)
        nxt = min((j for j in timed if j > i), default=None)
        if prev is None or nxt is None:
            continue  # leading/trailing gaps stay untimed rather than guessed
        gap_start = segments[prev].end_time_seconds
        gap_end = segments[nxt].start_time_seconds
        span = [j for j in range(len(segments))
                if prev < j < nxt and segments[j].start_time_seconds is None]
        k = span.index(i)
        n = len(span)
        seg.start_time_seconds = round(gap_start + (gap_end - gap_start) * k / n, 3)
        seg.end_time_seconds = round(gap_start + (gap_end - gap_start) * (k + 1) / n, 3)
