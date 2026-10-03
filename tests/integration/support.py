"""Shared source/fixture locations for standalone integration checks."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
WORKERS = ROOT / "src" / "blender_pipeline" / "blender"
FIXTURES = ROOT / "tests" / "fixtures"
