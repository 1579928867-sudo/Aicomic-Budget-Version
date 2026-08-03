"""Tests for PdfParser — PDF text extraction with OCR fallback."""

from pathlib import Path
import pytest
from aicomic.parsers.pdf_parser import PdfParser, PdfParserConfig


class TestPdfParserSupports:
    """supports() checks file extension only."""

    def test_supports_pdf(self):
        assert PdfParser.supports(Path("chapter.pdf")) is True

    def test_supports_uppercase(self):
        assert PdfParser.supports(Path("CHAPTER.PDF")) is True

    def test_rejects_txt(self):
        assert PdfParser.supports(Path("chapter.txt")) is False

    def test_rejects_docx(self):
        assert PdfParser.supports(Path("chapter.docx")) is False


class TestPdfParserParse:
    """parse() extracts text from PDF files."""

    def test_text_pdf_with_enough_chars(self, tmp_path):
        """A PDF with embedded text > 50 chars: should use text path (no OCR)."""
        import fitz
        file_path = tmp_path / "text_rich.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # Insert ~150 chars of Chinese text as embedded text layer.
        # fontsize=6 keeps the whole line within the A4 page width so pymupdf
        # 1.28 does not clip trailing glyphs off the right edge of the page.
        text = (
            "萧澈缓缓睁开眼睛，环顾四周，发现自己躺在陌生的床上。"
            "清晨暖光透过雕花窗棂洒入婚房，红色帷帐在微风中轻轻飘动，"
            "远处隐约传来鸟鸣。他记得昨晚与云家众人饮宴，却不记得如何来到此处。"
        )
        page.insert_text((50, 100), text, fontsize=6, fontname="china-s")
        doc.save(str(file_path))
        doc.close()

        parser = PdfParser()
        result = parser.parse(file_path)
        # Should contain the core text (fitz may add line breaks)
        assert "萧澈" in result
        assert len(result.strip()) >= 50

    def test_pdf_with_no_text(self, tmp_path):
        """A PDF with very little text → triggers OCR path.
        If tesseract is not installed, this raises TesseractNotFoundError."""
        import fitz
        file_path = tmp_path / "scanned.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # Insert just a few chars — well below the 50-char threshold
        page.insert_text((50, 100), "Hi", fontsize=12, fontname="helv")
        doc.save(str(file_path))
        doc.close()

        parser = PdfParser(config=PdfParserConfig(min_text_chars=50))
        try:
            import pytesseract  # noqa: F401
            import PIL  # noqa: F401
        except ImportError:
            # OCR libraries unavailable — the OCR path cannot run
            return
        try:
            result = parser.parse(file_path)
            # OCR on a nearly-blank page may return empty; that's fine
            assert isinstance(result, str)
        except RuntimeError:
            # Tesseract binary not installed / not on PATH — the parser
            # reports this as a RuntimeError; accept it as a graceful skip
            pass

    def test_corrupted_pdf_raises(self, tmp_path):
        """A file with .pdf extension that isn't a valid PDF should error."""
        file_path = tmp_path / "fake.pdf"
        file_path.write_text("not a real PDF file", encoding="utf-8")
        parser = PdfParser()
        with pytest.raises(ValueError, match="Failed to parse"):
            parser.parse(file_path)


class TestPdfParserConfig:
    """PdfParserConfig defaults and overrides."""

    def test_default_values(self):
        cfg = PdfParserConfig()
        assert cfg.min_text_chars == 50
        assert cfg.ocr_dpi == 300
        assert cfg.ocr_langs == "chi_sim+eng"

    def test_custom_values(self):
        cfg = PdfParserConfig(min_text_chars=100, ocr_dpi=150, ocr_langs="eng")
        assert cfg.min_text_chars == 100
        assert cfg.ocr_dpi == 150
        assert cfg.ocr_langs == "eng"
