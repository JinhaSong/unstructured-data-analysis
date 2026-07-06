"""Dependency-free smoke tests: txt parsing, ASR alignment, windowing, summary.

Run from the udav1 repo root's parent (so `udav1` is importable), or rely on
the path shim below.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from udav1.analyze.align import align_segments_to_asr          # noqa: E402
from udav1.analyze.summarize import summarize_window            # noqa: E402
from udav1.analyze.window import build_windows, gap_windows     # noqa: E402
from udav1.ingest.txt_parser import TxtParser                   # noqa: E402
from udav1.pipeline import analyze_path                         # noqa: E402
from udav1.schema import Segment                                # noqa: E402
from udav1.utils import parse_timecode                          # noqa: E402

SUBTITLE_CP949 = """.
-여러분, 안녕하십니까?
충북 시사토론 창입니다.
.
-(해설) 행복한 삶은
도시에서만 꿈꿀 수 있을까요?
"""

ARTICLE = "﻿순서: 10\n제목: 제천 상가 화재\n기자: 이초원\n기사 ID: 13184932\n\n[앵커멘트]\n\n[기사본문]\n오늘 오후 5시쯤\n불이 났습니다.\n\n[자막]\n제천 상가 화재\n\n화면제공/제천소방서\n"


def _write(text, encoding):
    fp = tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False)
    fp.write(text.encode(encoding))
    fp.close()
    return fp.name


class TestTimecode(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_timecode("02:20"), 140.0)
        self.assertEqual(parse_timecode("00:48:54"), 2934.0)
        self.assertAlmostEqual(parse_timecode("00:48:54:15"), 2934.5)
        self.assertEqual(parse_timecode("48: 54"), 2934.0)  # DUR with space
        self.assertIsNone(parse_timecode("n/a"))


class TestTxtParser(unittest.TestCase):
    def test_subtitle_cp949(self):
        path = _write(SUBTITLE_CP949, "cp949")
        raw = TxtParser().parse(path)
        self.assertEqual(raw.encoding, "cp949")
        # wrapped continuation lines merge into their speaker turn -> 2 blocks
        self.assertEqual(len(raw.text_blocks), 2)
        self.assertIn("충북 시사토론 창입니다", raw.text_blocks[0])
        self.assertEqual(raw.meta["turns"][1]["speaker"], "해설")
        os.unlink(path)

    def test_article_utf8_bom(self):
        path = _write(ARTICLE, "utf-8-sig")
        raw = TxtParser().parse(path)
        self.assertEqual(raw.meta["title"], "제천 상가 화재")
        self.assertEqual(raw.meta["reporter"], "이초원")
        self.assertIn("불이 났습니다", raw.text_blocks[0])
        os.unlink(path)


class TestAlign(unittest.TestCase):
    def test_graft_and_interpolate(self):
        segs = [Segment("d#0", "안 팔아 뭐예요 당신?"),
                Segment("d#1", "누구겠어?"),
                Segment("d#2", "여기 주인이요?")]
        asr = [
            {"start_time_seconds": 65.0, "end_time_seconds": 67.0, "text": "안 팔아 뭐예요 당신"},
            {"start_time_seconds": 67.0, "end_time_seconds": 69.2, "text": "누구겠어"},
            {"start_time_seconds": 69.2, "end_time_seconds": 70.8, "text": "여기 주인이요"},
        ]
        align_segments_to_asr(segs, asr)
        self.assertAlmostEqual(segs[0].start_time_seconds, 65.0, delta=0.3)
        self.assertAlmostEqual(segs[2].end_time_seconds, 70.8, delta=0.3)
        # monotonic
        self.assertLess(segs[0].end_time_seconds, segs[2].start_time_seconds + 0.01)


class TestWindowSummary(unittest.TestCase):
    def _segs(self):
        return [
            Segment("d#0", "첫 번째 화재 소식입니다.", start_time_seconds=0, end_time_seconds=5),
            Segment("d#1", "상가에서 불이 났습니다.", start_time_seconds=5, end_time_seconds=9),
            Segment("d#2", "다음은 날씨입니다.", start_time_seconds=20, end_time_seconds=24),
        ]

    def test_gap_windows(self):
        wins = gap_windows(self._segs(), gap_seconds=2.0)
        self.assertEqual(len(wins), 2)
        self.assertEqual(len(wins[0].segments), 2)

    def test_summary_is_extractive(self):
        wins = gap_windows(self._segs(), gap_seconds=2.0)
        tcs = summarize_window(wins[0], max_sentences=1)
        self.assertEqual(tcs.start_time_seconds, 0)
        self.assertEqual(tcs.end_time_seconds, 9)
        self.assertIn(tcs.summary, ("첫 번째 화재 소식입니다.", "상가에서 불이 났습니다."))
        self.assertTrue(tcs.source_seg_ids)


class TestPipelineEndToEnd(unittest.TestCase):
    def test_subtitle_with_asr(self):
        path = _write(".\n-안 팔아 뭐예요 당신?\n.\n-누구겠어? 이럴 수 있는 사람이\n", "cp949")
        asr = [
            {"start_time_seconds": 65.0, "end_time_seconds": 67.0, "text": "안 팔아 뭐예요 당신"},
            {"start_time_seconds": 67.0, "end_time_seconds": 69.2, "text": "누구겠어 이럴 수 있는 사람이"},
        ]
        result = analyze_path(path, "subtitle_script", asr)
        self.assertEqual(result.doc_type, "subtitle_script")
        self.assertTrue(result.time_coded_summaries)
        first = result.time_coded_summaries[0]
        self.assertIsNotNone(first.start_time_seconds)
        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
