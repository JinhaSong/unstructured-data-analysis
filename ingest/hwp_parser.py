""".hwp parser -- interview cuesheets & scripts (Hangul Word Processor 5.x).

Backend: hwplib (Apache-2.0, vendored at libs/hwplib as a submodule -- the
only commercially-safe HWP reader; pyhwp is GPL) bridged over JPype1
(Apache-2.0). Requires:

    1. a JVM (JAVA_HOME or system default)
    2. the hwplib jar:  cd libs/hwplib && mvn -q package
       (or set UDA_HWPLIB_JAR=/path/to/hwplib-x.y.z.jar)

Fallback: LibreOffice headless (`soffice --convert-to txt`) if present.
"""
import glob
import os
import subprocess
import tempfile

from .base import BaseParser, RawDoc

_JVM_STARTED = False


def _find_jar() -> str | None:
    env = os.environ.get("UDA_HWPLIB_JAR")
    if env and os.path.exists(env):
        return env
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hits = sorted(glob.glob(os.path.join(here, "libs", "hwplib", "target", "hwplib-*.jar")))
    hits = [j for j in hits if "sources" not in j and "javadoc" not in j]
    return hits[-1] if hits else None


def _extract_with_hwplib(path: str) -> list[str]:
    global _JVM_STARTED
    import jpype  # lazy

    jar = _find_jar()
    if jar is None:
        raise FileNotFoundError(
            "hwplib jar not found: build it (cd libs/hwplib && mvn package) "
            "or set UDA_HWPLIB_JAR")
    if not _JVM_STARTED and not jpype.isJVMStarted():
        jpype.startJVM(classpath=[jar])
        _JVM_STARTED = True

    HWPReader = jpype.JClass("kr.dogfoot.hwplib.reader.HWPReader")
    TextExtractor = jpype.JClass("kr.dogfoot.hwplib.tool.textextractor.TextExtractor")
    TextExtractMethod = jpype.JClass(
        "kr.dogfoot.hwplib.tool.textextractor.TextExtractMethod")

    hwp = HWPReader.fromFile(path)
    text = str(TextExtractor.extract(
        hwp, TextExtractMethod.InsertControlTextBetweenParagraphText))
    return [p.strip() for p in text.split("\n") if p.strip()]


def _extract_with_soffice(path: str) -> list[str]:
    from .encoding import decode_bytes
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "txt:Text", "--outdir", tmp, path],
            check=True, capture_output=True, timeout=120)
        out = glob.glob(os.path.join(tmp, "*.txt"))
        if not out:
            raise RuntimeError("soffice produced no output")
        with open(out[0], "rb") as fp:
            text, _ = decode_bytes(fp.read())
    return [p.strip() for p in text.split("\n") if p.strip()]


class HwpParser(BaseParser):
    def parse(self, path: str, hint: str | None = None) -> RawDoc:
        try:
            blocks = _extract_with_hwplib(path)
            backend = "hwplib"
        except Exception:
            blocks = _extract_with_soffice(path)
            backend = "soffice"
        return RawDoc(source_path=path, source_format="hwp",
                      text_blocks=blocks, meta={"backend": backend})
