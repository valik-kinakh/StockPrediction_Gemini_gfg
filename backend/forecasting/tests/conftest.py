"""Shared pytest configuration."""

import sys
from pathlib import Path

# Make `forecasting`, `predictor`, etc. importable from anywhere.
BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
