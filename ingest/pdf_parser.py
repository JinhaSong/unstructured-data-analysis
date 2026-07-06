""".pdf parser -- discussion/interview cuesheets & scripts.

Backend order: Docling (MIT, layout+table aware) if installed, else
pdfplumber (MIT, text + lattice tables). Both are commercially safe;
Marker was rejected (GPL-3.0 code + OpenRAIL-M weights, $2M revenue cap).
"""
from .base import BaseParser, RawDoc


class PdfParser(BaseParser):
    def parse(self, path: str, hint: str | None = None) -> RawDoc:
        try:
            return self._parse_docling(path)
        except ImportError:
            return self._parse_pdfplumber(path)

    def _parse_docling(self, path: str) -> RawDoc:
        from docling.document_converter import DocumentConverter  # lazy

        result = DocumentConverter().convert(path)
        doc = result.document
        blocks = [t for t in doc.export_to_markdown().split("\n\n") if t.strip()]
        tables = []
        for table in getattr(doc, "tables", []):
            try:
                df = table.export_to_dataframe()
                tables.append([[str(c) for c in row] for row in
                               [df.columns.tolist()] + df.values.tolist()])
            except Exception:
                continue
        return RawDoc(source_path=path, source_format="pdf",
                      text_blocks=blocks, tables=tables,
                      meta={"backend": "docling"})

    def _parse_pdfplumber(self, path: str) -> RawDoc:
        import pdfplumber  # lazy

        blocks, tables = [], []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                blocks.extend(p.strip() for p in text.split("\n\n") if p.strip())
                for table in page.extract_tables() or []:
                    tables.append([["" if c is None else str(c).strip() for c in row]
                                   for row in table])
        return RawDoc(source_path=path, source_format="pdf",
                      text_blocks=blocks, tables=tables,
                      meta={"backend": "pdfplumber"})
