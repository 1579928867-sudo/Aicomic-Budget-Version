"""Allow `python -m server` invocation."""
import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())

