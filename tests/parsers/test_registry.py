"""Integration tests for parsers registry and parse_file() entry point."""

from pathlib import Path
import pytest
from aicomic.parsers import (
    parse_file,
    detect_format,
    UnsupportedFormatError,
    PARSER_REGISTRY,
)


class TestRegistry:
    """The PARSER_REGISTRY contains all format parsers."""

    def test_registry_has_three_parsers(self):
        assert len(PARSER_REGISTRY) == 3

    def test_parsers_are_in_priority_order(self):
        """TxtParser first (fastest), Docx second, Pdf last (potentially slowest)."""
        names = [type(p).__name__ for p in PARSER_REGISTRY]
        assert names[0] == "TxtParser"
        assert names[1] == "DocxParser"
        assert names[2] == "PdfParser"


class TestDetectFormat:
    """detect_format() returns the parser class name for a supported file."""

    def test_detect_txt(self):
        assert detect_format(Path("chapter.txt")) == "TxtParser"

    def test_detect_docx(self):
        assert detect_format(Path("chapter.docx")) == "DocxParser"

    def test_detect_pdf(self):
        assert detect_format(Path("chapter.pdf")) == "PdfParser"

    def test_detect_unknown(self):
        assert detect_format(Path("data.bin")) == "unknown"


class TestParseFile:
    """parse_file() dispatches to the correct parser and returns text."""

    def test_parse_txt(self, tmp_path):
        content = "萧澈缓缓睁开眼睛。"
        file_path = tmp_path / "test.txt"
        file_path.write_text(content, encoding="utf-8")
        result = parse_file(file_path)
        assert result == content

    def test_parse_docx(self, tmp_path):
        from docx import Document
        file_path = tmp_path / "test.docx"
        doc = Document()
        doc.add_paragraph("萧澈缓缓睁开眼睛。")
        doc.save(str(file_path))
        result = parse_file(file_path)
        assert "萧澈缓缓睁开眼睛。" in result

    def test_parse_pdf(self, tmp_path):
        import fitz
        file_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # 75+ chars exceeds the default 50-char min_text_chars threshold, so the
        # embedded-text path is used (no OCR). fontsize=6 keeps the whole line
        # within the A4 page width so PyMuPDF does not clip trailing glyphs.
        text = (
            "萧澈缓缓睁开眼睛，环顾四周。清晨暖光透过雕花窗棂洒入婚房，"
            "红色帷帐在微风中轻轻飘动，远处隐约传来鸟鸣。"
            "他记得昨夜与云家众人饮宴，却不记得如何来到此处。"
        )
        page.insert_text((50, 100), text, fontsize=6, fontname="china-s")
        doc.save(str(file_path))
        doc.close()
        result = parse_file(file_path)
        assert len(result.strip()) >= 10
        assert "萧澈" in result

    def test_unsupported_format_raises(self, tmp_path):
        file_path = tmp_path / "data.bin"
        file_path.write_bytes(b"\x00\x01\x02")
        with pytest.raises(UnsupportedFormatError) as excinfo:
            parse_file(file_path)
        assert ".bin" in str(excinfo.value)
        assert ".txt" in str(excinfo.value)
        assert ".docx" in str(excinfo.value)
        assert ".pdf" in str(excinfo.value)

    def test_missing_file_raises(self, tmp_path):
        file_path = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError):
            parse_file(file_path)
