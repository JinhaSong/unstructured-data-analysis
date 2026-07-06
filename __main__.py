"""Standalone test:  python -m udav1 <file> [--type cuesheet] [--asr asr.json]

Run from the directory containing ``udav1/`` (e.g. libs/ud) or with it on
PYTHONPATH. Prints the UDResult as JSON.
"""
import argparse
import json

from .pipeline import analyze_path


def main():
    ap = argparse.ArgumentParser(prog="python -m udav1")
    ap.add_argument("path", help="unstructured file (.txt/.xlsx/.xml/.pdf/.hwp)")
    ap.add_argument("--type", dest="doc_type", default=None,
                    choices=["cuesheet", "narration", "schedule",
                             "subtitle_script", "clip_meta"])
    ap.add_argument("--asr", default=None,
                    help="faster-whisper transcript JSON (with 'segments')")
    args = ap.parse_args()

    asr_segments = None
    if args.asr:
        with open(args.asr, encoding="utf-8") as fp:
            data = json.load(fp)
        asr_segments = data.get("segments", data)

    result = analyze_path(args.path, args.doc_type, asr_segments)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
