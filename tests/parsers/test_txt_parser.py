"""Tests for TxtParser — multi-encoding text file parsing."""

from pathlib import Path
import pytest
from aicomic.parsers.txt_parser import TxtParser


class TestTxtParserSupports:
    """supports() checks file extension only."""

    def test_supports_txt_lowercase(self):
        assert TxtParser.supports(Path("chapter.txt")) is True

    def test_supports_txt_uppercase(self):
        assert TxtParser.supports(Path("CHAPTER.TXT")) is True

    def test_supports_txt_mixed_case(self):
        assert TxtParser.supports(Path("Chapter.Txt")) is True

    def test_rejects_docx(self):
        assert TxtParser.supports(Path("chapter.docx")) is False

    def test_rejects_pdf(self):
        assert TxtParser.supports(Path("chapter.pdf")) is False

    def test_rejects_no_extension(self):
        assert TxtParser.supports(Path("README")) is False


class TestTxtParserParse:
    """parse() extracts text with encoding auto-detection."""

    def test_utf8_file(self, tmp_path):
        content = "萧澈缓缓睁开眼睛，环顾四周。\n第二章开始。"
        file_path = tmp_path / "chapter.txt"
        file_path.write_text(content, encoding="utf-8")
        parser = TxtParser()
        result = parser.parse(file_path)
        assert result == content

    def test_gbk_file(self, tmp_path):
        content = "萧澈缓缓睁开眼睛，环顾四周。"
        file_path = tmp_path / "chapter.txt"
        file_path.write_text(content, encoding="gbk")
        parser = TxtParser()
        result = parser.parse(file_path)
        assert result == content

    def test_gb18030_file(self, tmp_path):
        content = "云澈、萧澈——逆天邪神第一章"
        file_path = tmp_path / "chapter.txt"
        file_path.write_text(content, encoding="gb18030")
        parser = TxtParser()
        result = parser.parse(file_path)
        assert result == content

    def test_empty_file_returns_empty(self, tmp_path):
        file_path = tmp_path / "empty.txt"
        file_path.write_text("", encoding="utf-8")
        parser = TxtParser()
        result = parser.parse(file_path)
        assert result == ""

    def test_undecodable_file_raises(self, tmp_path):
        """A file that isn't valid in any known encoding should raise ValueError."""
        file_path = tmp_path / "binary.txt"
        # Write raw bytes that are not valid in utf-8, gbk, or gb18030
        file_path.write_bytes(b"\x80\x81\x82\x83\x84\x85")
        parser = TxtParser()
        with pytest.raises(ValueError, match="Cannot decode"):
            parser.parse(file_path)
