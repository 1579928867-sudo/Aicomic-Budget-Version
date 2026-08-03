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
