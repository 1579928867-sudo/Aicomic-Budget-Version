"""Plain-text file parser with multi-encoding auto-detection."""

from pathlib import Path


class TxtParser:
    """Parses .txt files with automatic encoding detection.

    Tries encodings in priority order: utf-8-sig → utf-8 → gbk → gb18030.
    This covers virtually all Chinese web novel files and strips BOMs.
    """

    _ENCODINGS = ["utf-8-sig", "utf-8", "gbk", "gb18030"]

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
