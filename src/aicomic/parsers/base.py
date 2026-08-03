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
