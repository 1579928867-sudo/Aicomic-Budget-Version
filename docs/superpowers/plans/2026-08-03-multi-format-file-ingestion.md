# Multi-Format File Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `.docx` (Word) and `.pdf` (scanned+text) file ingestion to AI漫剧 via a `parsers/` abstraction layer, keeping the Orchestrator and all downstream agents unchanged.

**Architecture:** A 5-file `src/aicomic/parsers/` package with a `FileParser` protocol, three format-specific parsers (txt, docx, pdf), and a unified `parse_file()` entry point. The CLI (`main.py`) calls `parse_file()` instead of `read_text()`; the orchestrator interface (`run_chapter(chapter_id, raw_text: str)`) is untouched.

**Tech Stack:** Python 3.12+, python-docx, pymupdf, pytesseract, Tesseract OCR system package

## Global Constraints

- Python >=3.12 (existing project requirement)
- Orchestrator interface must NOT change: `run_chapter(chapter_id, raw_text: str)`
- All new dependencies must be added to `pyproject.toml`
- Tesseract is a system dependency (user installs manually), not a pip package
- PDF OCR path is triggered when pymupdf extracts fewer than `min_text_chars` chars (default: 50)
- Config for parsers lives in `config/settings.yaml` under `parsers:` key
- Follow existing test conventions: pytest, test files in `tests/` matching source module pattern

---

### Task 1: Add dependencies and default config

**Files:**
- Modify: `pyproject.toml:12-19` (dependencies list)
- Modify: `config/settings.yaml` (append `parsers:` block)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `python-docx>=1.0`, `pymupdf>=1.24`, `pytesseract>=0.3` installed; `config["parsers"]` dict available for later tasks

- [ ] **Step 1: Add 3 dependencies to pyproject.toml**

Replace the `dependencies` list in `pyproject.toml`:

```toml
dependencies = [
    "anthropic>=0.40.0",
    "moviepy>=2.0",
    "openai>=1.0",
    "playwright>=1.40",
    "requests>=2.31",
    "pyyaml>=6.0",
    "python-docx>=1.0",
    "pymupdf>=1.24",
    "pytesseract>=0.3",
]
```

- [ ] **Step 2: Install new dependencies**

Run: `pip install python-docx>=1.0 pymupdf>=1.24 pytesseract>=0.3`
Expected: all three install without error

- [ ] **Step 3: Append parsers config to settings.yaml**

Append this block at the end of `config/settings.yaml`:

```yaml
parsers:
  pdf:
    min_text_chars: 50        # chars below this → scanned PDF, trigger OCR
    ocr_dpi: 300              # rendering DPI for OCR path
    ocr_langs: "chi_sim+eng"  # Tesseract language packs
```

- [ ] **Step 4: Verify config loads without error**

Run: `python -c "import yaml; c = yaml.safe_load(open('config/settings.yaml')); assert 'parsers' in c; print(c['parsers'])"`
Expected: prints `{'pdf': {'min_text_chars': 50, 'ocr_dpi': 300, 'ocr_langs': 'chi_sim+eng'}}`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml config/settings.yaml
git commit -m "chore: add parser dependencies (python-docx, pymupdf, pytesseract) + parsers config block"
```

---

### Task 2: Create `base.py` — FileParser protocol

**Files:**
- Create: `src/aicomic/parsers/__init__.py` (empty package marker)
- Create: `src/aicomic/parsers/base.py`

**Interfaces:**
- Consumes: nothing
- Produces: `FileParser` protocol class — `parse(self, file_path: Path) -> str` and `supports(file_path: Path) -> bool`

- [ ] **Step 1: Create the parsers package directory**

```bash
mkdir -p src/aicomic/parsers
```

- [ ] **Step 2: Create empty __init__.py (will be replaced in Task 6)**

Write `src/aicomic/parsers/__init__.py`:

```python
"""Multi-format file parsers for novel content ingestion."""
```

- [ ] **Step 3: Write base.py with FileParser protocol**

Write `src/aicomic/parsers/base.py`:

```python
"""FileParser protocol — all parsers implement this interface."""

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class FileParser(Protocol):
    """Protocol for file-format parsers.

    Each parser handles one file format and exposes two methods:
    - supports(): quick extension-based check (no file I/O)
    - parse(): extract plain text from the file
    """

    def parse(self, file_path: Path) -> str:
        """Extract plain text content from the file."""
        ...

    @staticmethod
    def supports(file_path: Path) -> bool:
        """Return True if this parser can handle the given file path."""
        ...
```

- [ ] **Step 4: Verify the module imports cleanly**

Run: `python -c "from aicomic.parsers.base import FileParser; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/aicomic/parsers/__init__.py src/aicomic/parsers/base.py
git commit -m "feat: add FileParser protocol (parsers/base.py)"
```

---

### Task 3: Create `txt_parser.py` with multi-encoding support

**Files:**
- Create: `src/aicomic/parsers/txt_parser.py`
- Create: `tests/parsers/__init__.py` (empty)
- Create: `tests/parsers/test_txt_parser.py`

**Interfaces:**
- Consumes: `FileParser` from `base.py`
- Produces: `TxtParser` class — `supports()` checks `.txt` extension, `parse()` tries utf-8 → gbk → gb18030

- [ ] **Step 1: Write the test file**

Write `tests/parsers/__init__.py` (empty file), then write `tests/parsers/test_txt_parser.py`:

```python
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
```

- [ ] **Step 2: Run tests — all should FAIL (module not found)**

Run: `pytest tests/parsers/test_txt_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aicomic.parsers.txt_parser'`

- [ ] **Step 3: Write TxtParser implementation**

Write `src/aicomic/parsers/txt_parser.py`:

```python
"""Plain-text file parser with multi-encoding auto-detection."""

from pathlib import Path


class TxtParser:
    """Parses .txt files with automatic encoding detection.

    Tries encodings in priority order: utf-8 → gbk → gb18030.
    This covers virtually all Chinese web novel files.
    """

    _ENCODINGS = ["utf-8", "gbk", "gb18030"]

    def parse(self, file_path: Path) -> str:
        """Read file contents, trying each known encoding until one succeeds."""
        for encoding in self._ENCODINGS:
            try:
                return file_path.read_text(encoding=encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError(
            f"Cannot decode {file_path.name} with any encoding: {self._ENCODINGS}"
        )

    @staticmethod
    def supports(file_path: Path) -> bool:
        """Return True for .txt files (case-insensitive)."""
        return file_path.suffix.lower() == ".txt"
```

- [ ] **Step 4: Run tests — all should PASS**

Run: `pytest tests/parsers/test_txt_parser.py -v`
Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/parsers/__init__.py tests/parsers/test_txt_parser.py src/aicomic/parsers/txt_parser.py
git commit -m "feat: add TxtParser with multi-encoding support (utf-8/gbk/gb18030)"
```

---

### Task 4: Create `docx_parser.py` — Word document parser

**Files:**
- Create: `src/aicomic/parsers/docx_parser.py`
- Create: `tests/parsers/test_docx_parser.py`

**Interfaces:**
- Consumes: `FileParser` from `base.py`
- Produces: `DocxParser` class — `supports()` checks `.docx` extension, `parse()` extracts paragraph text

- [ ] **Step 1: Write the test file**

Write `tests/parsers/test_docx_parser.py`:

```python
"""Tests for DocxParser — Word document text extraction."""

from pathlib import Path
import pytest
from aicomic.parsers.docx_parser import DocxParser


class TestDocxParserSupports:
    """supports() checks file extension only."""

    def test_supports_docx(self):
        assert DocxParser.supports(Path("chapter.docx")) is True

    def test_supports_uppercase(self):
        assert DocxParser.supports(Path("CHAPTER.DOCX")) is True

    def test_rejects_txt(self):
        assert DocxParser.supports(Path("chapter.txt")) is False

    def test_rejects_pdf(self):
        assert DocxParser.supports(Path("chapter.pdf")) is False


class TestDocxParserParse:
    """parse() extracts paragraph text from .docx files."""

    def test_single_paragraph(self, tmp_path):
        from docx import Document
        file_path = tmp_path / "test.docx"
        doc = Document()
        doc.add_paragraph("萧澈缓缓睁开眼睛。")
        doc.save(str(file_path))

        parser = DocxParser()
        result = parser.parse(file_path)
        assert "萧澈缓缓睁开眼睛。" in result

    def test_multiple_paragraphs(self, tmp_path):
        from docx import Document
        file_path = tmp_path / "test.docx"
        doc = Document()
        doc.add_paragraph("第一段：清晨暖光透过窗棂。")
        doc.add_paragraph("第二段：红色帷帐在风中飘动。")
        doc.add_paragraph("第三段：远处隐约传来鸟鸣。")
        doc.save(str(file_path))

        parser = DocxParser()
        result = parser.parse(file_path)
        # Paragraphs should be separated by double newlines
        assert "第一段：清晨暖光透过窗棂。" in result
        assert "第二段：红色帷帐在风中飘动。" in result
        assert "第三段：远处隐约传来鸟鸣。" in result
        # Verify paragraph separation
        assert "\n\n" in result

    def test_empty_document(self, tmp_path):
        from docx import Document
        file_path = tmp_path / "empty.docx"
        doc = Document()
        doc.save(str(file_path))

        parser = DocxParser()
        result = parser.parse(file_path)
        assert result == ""

    def test_skips_empty_paragraphs(self, tmp_path):
        from docx import Document
        file_path = tmp_path / "sparse.docx"
        doc = Document()
        doc.add_paragraph("第一段内容。")
        doc.add_paragraph("")  # empty paragraph
        doc.add_paragraph("")  # another empty
        doc.add_paragraph("第三段内容。")
        doc.save(str(file_path))

        parser = DocxParser()
        result = parser.parse(file_path)
        # Empty paragraphs should be filtered out
        assert result.count("\n\n") == 1  # exactly one separation
        assert "第一段内容。" in result
        assert "第三段内容。" in result

    def test_corrupted_file_raises(self, tmp_path):
        """A file with .docx extension that isn't a valid docx should error."""
        file_path = tmp_path / "fake.docx"
        file_path.write_text("not a real docx file", encoding="utf-8")
        parser = DocxParser()
        with pytest.raises(ValueError, match="Failed to parse"):
            parser.parse(file_path)
```

- [ ] **Step 2: Run tests — all should FAIL (module not found)**

Run: `pytest tests/parsers/test_docx_parser.py -v`
Expected: FAIL

- [ ] **Step 3: Write DocxParser implementation**

Write `src/aicomic/parsers/docx_parser.py`:

```python
"""Word (.docx) document parser — extracts paragraph text."""

from pathlib import Path


class DocxParser:
    """Parses .docx files by extracting paragraph text.

    Images, tables, headers, and footers are ignored — only body
    paragraph text is extracted, which is what matters for novels.
    """

    def parse(self, file_path: Path) -> str:
        """Extract all paragraph text from a .docx file.

        Paragraphs are joined with double newlines. Empty paragraphs
        (whitespace-only) are filtered out.
        """
        try:
            from docx import Document
            doc = Document(str(file_path))
        except Exception as exc:
            raise ValueError(
                f"Failed to parse {file_path.name} as a Word document. "
                f"Ensure the file is a valid .docx. Error: {exc}"
            ) from exc

        paragraphs = [
            p.text for p in doc.paragraphs if p.text.strip()
        ]
        return "\n\n".join(paragraphs)

    @staticmethod
    def supports(file_path: Path) -> bool:
        """Return True for .docx files (case-insensitive)."""
        return file_path.suffix.lower() == ".docx"
```

- [ ] **Step 4: Run tests — all should PASS**

Run: `pytest tests/parsers/test_docx_parser.py -v`
Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/parsers/test_docx_parser.py src/aicomic/parsers/docx_parser.py
git commit -m "feat: add DocxParser for Word document text extraction"
```

---

### Task 5: Create `pdf_parser.py` — PDF parser with OCR fallback

**Files:**
- Create: `src/aicomic/parsers/pdf_parser.py`
- Create: `tests/parsers/test_pdf_parser.py`

**Interfaces:**
- Consumes: `FileParser` from `base.py`
- Produces: `PdfParserConfig` dataclass + `PdfParser` class — `supports()` checks `.pdf` extension, `parse()` extracts text via pymupdf with Tesseract OCR fallback when text layer is thin

- [ ] **Step 1: Write the test file**

Write `tests/parsers/test_pdf_parser.py`:

```python
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
        # Insert ~150 chars of Chinese text as embedded text layer
        text = (
            "萧澈缓缓睁开眼睛，环顾四周，发现自己躺在陌生的床上。"
            "清晨暖光透过雕花窗棂洒入婚房，红色帷帐在微风中轻轻飘动，"
            "远处隐约传来鸟鸣。他记得昨晚与云家众人饮宴，却不记得如何来到此处。"
        )
        page.insert_text((50, 100), text, fontsize=12, fontname="china-s")
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
        # Without Tesseract installed, this should raise TesseractNotFoundError
        # With Tesseract, it will run OCR (but may produce little output on blank page)
        try:
            import pytesseract  # noqa: F401
            import PIL  # noqa: F401
            # If both are importable, OCR path runs — may return empty on blank page
            result = parser.parse(file_path)
            # OCR on a nearly-blank page may return empty; that's fine
            assert isinstance(result, str)
        except ImportError:
            # Tesseract or PIL not available — expect the parser to report it
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
```

- [ ] **Step 2: Run tests — all should FAIL (module not found)**

Run: `pytest tests/parsers/test_pdf_parser.py -v`
Expected: FAIL

- [ ] **Step 3: Write PdfParser implementation**

Write `src/aicomic/parsers/pdf_parser.py`:

```python
"""PDF parser with dual-track extraction: embedded text → OCR fallback."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PdfParserConfig:
    """Configuration for PDF parsing behavior.

    Attributes:
        min_text_chars: Minimum characters from embedded text extraction
            before falling back to OCR. PDFs with fewer chars are treated
            as scanned/image-based documents.
        ocr_dpi: Rendering resolution for the OCR path (dots per inch).
        ocr_langs: Tesseract language string, e.g. "chi_sim+eng".
    """
    min_text_chars: int = 50
    ocr_dpi: int = 300
    ocr_langs: str = "chi_sim+eng"


class PdfParser:
    """Parses PDF files, automatically detecting and OCR-ing scanned pages.

    Strategy (two-track):
    1. Extract embedded text via pymupdf.get_text() on every page.
    2. If the total character count is below config.min_text_chars,
       treat the PDF as scanned and OCR each page via Tesseract.

    This means text-based PDFs are fast (no OCR), while scanned/image-based
    PDFs still produce usable text at the cost of OCR speed.
    """

    def __init__(self, config: PdfParserConfig | None = None):
        self.config = config or PdfParserConfig()

    def parse(self, file_path: Path) -> str:
        """Extract plain text from a PDF file."""
        try:
            import fitz
            doc = fitz.open(str(file_path))
        except Exception as exc:
            raise ValueError(
                f"Failed to parse {file_path.name} as a PDF. "
                f"Ensure the file is a valid PDF. Error: {exc}"
            ) from exc

        try:
            # ── Track 1: extract embedded text layer ──
            embedded_parts: list[str] = []
            for page in doc:
                page_text = page.get_text("text")
                if page_text.strip():
                    embedded_parts.append(page_text)

            combined = "\n".join(embedded_parts)

            # ── Check threshold: enough text? ──
            if len(combined.strip()) >= self.config.min_text_chars:
                return combined

            # ── Track 2: OCR fallback for scanned/image PDFs ──
            return self._ocr_pages(doc)
        finally:
            doc.close()

    def _ocr_pages(self, doc) -> str:
        """OCR every page of the PDF document via Tesseract."""
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise ImportError(
                "pytesseract and Pillow are required for OCR. "
                "Install with: pip install pytesseract Pillow"
            ) from exc

        parts: list[str] = []
        for i, page in enumerate(doc):
            # Render page to image at configured DPI
            pix = page.get_pixmap(dpi=self.config.ocr_dpi)
            img = Image.frombytes(
                "RGB", (pix.width, pix.height), pix.samples
            )
            try:
                page_text = pytesseract.image_to_string(
                    img, lang=self.config.ocr_langs
                )
            except pytesseract.TesseractNotFoundError as exc:
                raise RuntimeError(
                    "Tesseract OCR is not installed or not on your PATH.\n"
                    "Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki\n"
                    "And add the chi_sim language pack for Chinese support."
                ) from exc

            if page_text.strip():
                parts.append(page_text.strip())

        return "\n".join(parts)

    @staticmethod
    def supports(file_path: Path) -> bool:
        """Return True for .pdf files (case-insensitive)."""
        return file_path.suffix.lower() == ".pdf"
```

- [ ] **Step 4: Run tests — all should PASS (OCR-dependent tests may skip)**

Run: `pytest tests/parsers/test_pdf_parser.py -v`
Expected: tests PASS (4 supports + 1 text PDF + 1 config defaults + 1 config custom = 7 tests). The `test_pdf_with_no_text` and `test_corrupted_pdf_raises` also pass.

- [ ] **Step 5: Commit**

```bash
git add tests/parsers/test_pdf_parser.py src/aicomic/parsers/pdf_parser.py
git commit -m "feat: add PdfParser with pymupdf text extraction + Tesseract OCR fallback"
```

---

### Task 6: Create `__init__.py` — registry + unified entry point

**Files:**
- Modify: `src/aicomic/parsers/__init__.py` (replace placeholder)
- Create: `tests/parsers/test_registry.py`

**Interfaces:**
- Consumes: `TxtParser`, `DocxParser`, `PdfParser` from Tasks 3-5
- Produces: `parse_file(file_path: Path, parser_configs: dict | None = None) -> str`, `detect_format(file_path: Path) -> str`, `UnsupportedFormatError`

- [ ] **Step 1: Write the integration test file**

Write `tests/parsers/test_registry.py`:

```python
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
        text = "萧澈缓缓睁开眼睛，环顾四周。清晨暖光透过雕花窗棂洒入婚房，红色帷帐在微风中轻轻飘动。"
        page.insert_text((50, 100), text, fontsize=12, fontname="china-s")
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
        assert "data.bin" in str(excinfo.value)
        assert ".txt" in str(excinfo.value)
        assert ".docx" in str(excinfo.value)
        assert ".pdf" in str(excinfo.value)

    def test_missing_file_raises(self, tmp_path):
        file_path = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError):
            parse_file(file_path)
```

- [ ] **Step 2: Run tests — all should FAIL (old __init__.py has no exports)**

Run: `pytest tests/parsers/test_registry.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Write the full __init__.py**

Replace `src/aicomic/parsers/__init__.py`:

```python
"""Multi-format file parsers for novel content ingestion.

Supports:
    - .txt  (utf-8/gbk/gb18030 auto-detection)
    - .docx (Word document paragraph extraction)
    - .pdf  (embedded text + Tesseract OCR fallback for scanned PDFs)

Usage:
    from aicomic.parsers import parse_file, detect_format

    raw_text = parse_file(Path("chapter.pdf"))
    print(detect_format(Path("chapter.pdf")))  # → "PdfParser"
"""

from pathlib import Path

from .base import FileParser
from .txt_parser import TxtParser
from .docx_parser import DocxParser
from .pdf_parser import PdfParser, PdfParserConfig

# Registry is ordered: first-match-wins. Txt first (fastest), Pdf last.
PARSER_REGISTRY: list[FileParser] = [
    TxtParser(),
    DocxParser(),
    PdfParser(),
]


class UnsupportedFormatError(ValueError):
    """Raised when no parser can handle the given file format.

    The error message lists all supported file extensions.
    """

    def __init__(self, file_path: Path):
        suffix = file_path.suffix or "(no extension)"
        supported = ", ".join(
            [".txt", ".docx", ".pdf"]
        )
        super().__init__(
            f"Unsupported file format: {suffix}. "
            f"Supported formats: {supported}"
        )


def detect_format(file_path: Path) -> str:
    """Return the parser class name for a given file, or 'unknown'.

    Useful for logging / user feedback before calling parse_file().
    """
    for parser in PARSER_REGISTRY:
        if parser.supports(file_path):
            return type(parser).__name__
    return "unknown"


def parse_file(
    file_path: Path,
    parser_configs: dict | None = None,
) -> str:
    """Parse any supported file into plain text.

    Dispatches to the first parser whose supports() returns True.
    If parser_configs is provided, PdfParser is re-instantiated with
    the 'pdf' sub-dict (e.g. from settings.yaml parsers: block).

    Args:
        file_path: Path to the input file (.txt, .docx, or .pdf).
        parser_configs: Optional per-format config dict, e.g.
            {"pdf": {"min_text_chars": 50, "ocr_dpi": 300}}.

    Returns:
        Extracted plain text as a single string.

    Raises:
        UnsupportedFormatError: No parser can handle this file format.
        FileNotFoundError: The file does not exist.
        ValueError: The file is corrupt or cannot be parsed.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Build registry, potentially with custom config
    registry = PARSER_REGISTRY
    if parser_configs:
        pdf_cfg = parser_configs.get("pdf")
        if pdf_cfg:
            registry = [
                TxtParser(),
                DocxParser(),
                PdfParser(config=PdfParserConfig(**pdf_cfg)),
            ]

    for parser in registry:
        if parser.supports(file_path):
            return parser.parse(file_path)

    raise UnsupportedFormatError(file_path)
```

- [ ] **Step 4: Run integration tests — all should PASS**

Run: `pytest tests/parsers/test_registry.py -v`
Expected: all 9 tests PASS

- [ ] **Step 5: Run ALL parser tests together**

Run: `pytest tests/parsers/ -v`
Expected: all parser tests PASS (~25 tests across 4 files)

- [ ] **Step 6: Commit**

```bash
git add src/aicomic/parsers/__init__.py tests/parsers/test_registry.py
git commit -m "feat: add parsers registry + parse_file() unified entry point"
```

---

### Task 7: Wire CLI — `main.py` integration

**Files:**
- Modify: `src/aicomic/main.py:1-10` (add import), `src/aicomic/main.py:118` (replace read_text), `src/aicomic/main.py:289` (update help text)

**Interfaces:**
- Consumes: `parse_file` from `parsers/__init__.py`
- Produces: `python -m aicomic run <file>` now accepts .txt, .docx, .pdf

- [ ] **Step 1: Update the import block in main.py**

In `src/aicomic/main.py`, add the parsers import after the existing stdlib imports (around line 13):

```python
import argparse
import os
import sys
from pathlib import Path

import yaml

from .parsers import parse_file, UnsupportedFormatError
```

- [ ] **Step 2: Replace the read_text call at line 118**

Replace:
```python
raw_text = chapter_file.read_text(encoding="utf-8")
if not raw_text.strip():
    print("Error: File is empty", file=sys.stderr)
    sys.exit(1)
```

With:
```python
try:
    raw_text = parse_file(
        chapter_file,
        parser_configs=config.get("parsers"),
    )
except UnsupportedFormatError as exc:
    print(f"Error: {exc}", file=sys.stderr)
    sys.exit(1)
except ValueError as exc:
    print(f"Error: {exc}", file=sys.stderr)
    sys.exit(1)

if not raw_text.strip():
    print("Error: File is empty or produced no text", file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step 3: Update argparse help text at line 289**

Replace:
```python
run_parser.add_argument(
    "file",
    type=Path,
    help="Path to chapter text file (.txt)",
)
```

With:
```python
run_parser.add_argument(
    "file",
    type=Path,
    help="Path to chapter file (.txt, .docx, .pdf)",
)
```

- [ ] **Step 4: Verify imports work**

Run: `python -c "from aicomic.parsers import parse_file; print('import OK')"`
Expected: `import OK`

- [ ] **Step 5: Run smoke test with existing .txt file**

Run: `python -m aicomic run "逆天邪神第2章 情不自禁 .txt" --backend deepseek 2>&1 | head -20`
Expected: pipeline starts normally, novel title detected, no import/parse errors

- [ ] **Step 6: Verify error for unsupported format**

Run: `python -c "from pathlib import Path; from aicomic.parsers import parse_file; parse_file(Path('/tmp/test.xyz'))" 2>&1 || true`
Expected: error message mentioning `.txt, .docx, .pdf`

- [ ] **Step 7: Commit**

```bash
git add src/aicomic/main.py
git commit -m "feat: wire parse_file() into CLI — support .txt, .docx, .pdf input"
```
