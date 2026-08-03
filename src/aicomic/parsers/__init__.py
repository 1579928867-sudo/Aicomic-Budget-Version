"""Multi-format file parsers for novel content ingestion.

Supports:
    - .txt  (utf-8-sig/utf-8/gbk/gb18030 auto-detection)
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
            try:
                registry = [
                    TxtParser(),
                    DocxParser(),
                    PdfParser(config=PdfParserConfig(**pdf_cfg)),
                ]
            except TypeError as exc:
                raise ValueError(f"Invalid parser config: {exc}") from exc

    for parser in registry:
        if parser.supports(file_path):
            return parser.parse(file_path)

    raise UnsupportedFormatError(file_path)
