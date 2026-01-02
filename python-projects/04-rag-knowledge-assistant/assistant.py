#!/usr/bin/env python3
"""Convenience wrapper to run the knowledge assistant."""

import sys
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from assistant import main

if __name__ == "__main__":
    main()
