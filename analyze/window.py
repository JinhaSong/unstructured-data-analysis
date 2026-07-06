"""P3 -- cut the document timeline into windows for per-window summarization.

Strategies (picked per doc_type in configs.py):
  item          each segment is its own window (cuesheet: one news item)
  speaker_turn  merge consecutive segments of the same speaker (discussion)
  gap           new window when the time gap between segments exceeds N sec
  fixed         tumbling N-second windows (fallback)
"""
from dataclasses import dataclass, field


@dataclass
class Window:
    start_time_seconds: float | None
    end_time_seconds: float | None
    segments: list = field(default_factory=list)
    speaker: str | None = None


def item_windows(segments, **_):
    return [Window(s.start_time_seconds, s.end_time_seconds, [s], s.speaker)
            for s in segments if s.text]


def speaker_turn_windows(segments, **_):
    windows = []
    for seg in segments:
        if windows and windows[-1].speaker == seg.speaker:
            w = windows[-1]
            w.segments.append(seg)
            if seg.end_time_seconds is not None:
                w.end_time_seconds = seg.end_time_seconds
        else:
            windows.append(Window(seg.start_time_seconds, seg.end_time_seconds,
                                  [seg], seg.speaker))
    return windows


def gap_windows(segments, gap_seconds: float = 2.0, **_):
    windows = []
    for seg in segments:
        prev = windows[-1] if windows else None
        start_new = (
            prev is None
            or seg.start_time_seconds is None
            or prev.end_time_seconds is None
            or seg.start_time_seconds - prev.end_time_seconds > gap_seconds)
        if start_new:
            windows.append(Window(seg.start_time_seconds, seg.end_time_seconds, [seg]))
        else:
            prev.segments.append(seg)
            prev.end_time_seconds = seg.end_time_seconds
    return windows


def fixed_windows(segments, window_seconds: float = 30.0, **_):
    timed = [s for s in segments if s.start_time_seconds is not None]
    untimed = [s for s in segments if s.start_time_seconds is None]
    buckets = {}
    for seg in timed:
        idx = int(seg.start_time_seconds // window_seconds)
        buckets.setdefault(idx, []).append(seg)
    windows = [Window(i * window_seconds, (i + 1) * window_seconds, segs)
               for i, segs in sorted(buckets.items())]
    if untimed:  # everything untimed collapses into one window (no better info)
        windows.append(Window(None, None, untimed))
    return windows


STRATEGIES = {
    "item": item_windows,
    "speaker_turn": speaker_turn_windows,
    "gap": gap_windows,
    "fixed": fixed_windows,
}


def build_windows(doc, strategy: str = "fixed", **kwargs):
    return STRATEGIES[strategy](doc.segments, **kwargs)
