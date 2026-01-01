#!/usr/bin/env python3
"""Convenience wrapper to run the generator from project root."""

import sys
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import and run the main function
from generator import main

if __name__ == "__main__":
    main()
