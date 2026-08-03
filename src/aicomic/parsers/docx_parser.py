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
