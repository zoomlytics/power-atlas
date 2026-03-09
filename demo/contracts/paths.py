from __future__ import annotations

from pathlib import Path

# Centralized filesystem locations for the demo.
BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "fixtures"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
CONFIG_DIR = BASE_DIR / "config"
PDF_PIPELINE_CONFIG_PATH = CONFIG_DIR / "pdf_simple_kg_pipeline.yaml"

__all__ = ["ARTIFACTS_DIR", "CONFIG_DIR", "FIXTURES_DIR", "PDF_PIPELINE_CONFIG_PATH"]
