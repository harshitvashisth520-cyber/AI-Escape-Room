"""Pytest configuration: add the project root to sys.path so the
`v2` and `shared` packages can be imported during test collection."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
