from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

# Centralized filesystem locations for the demo.
BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "fixtures"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
CONFIG_DIR = BASE_DIR / "config"
PDF_PIPELINE_CONFIG_PATH = CONFIG_DIR / "pdf_simple_kg_pipeline.yaml"

# Container directory that holds all named dataset roots.
DATASETS_CONTAINER_DIR = FIXTURES_DIR / "datasets"

_logger = logging.getLogger(__name__)

_DEFAULT_PDF_FILENAME = "chain_of_custody.pdf"


@dataclass(frozen=True)
class DatasetRoot:
    """Self-contained descriptor for a single fixture dataset.

    All path attributes are derived from :attr:`root` so callers never need
    to reconstruct sub-paths manually.
    """

    root: Path
    dataset_id: str
    pdf_filename: str

    @property
    def structured_dir(self) -> Path:
        return self.root / "structured"

    @property
    def unstructured_dir(self) -> Path:
        return self.root / "unstructured"

    @property
    def pdf_path(self) -> Path:
        return self.root / "unstructured" / self.pdf_filename

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"


def _load_dataset_root_from_dir(root: Path) -> DatasetRoot:
    """Read ``manifest.json`` inside *root* and construct a :class:`DatasetRoot`.

    Path values in the manifest's ``provenance`` list may be either
    dataset-root-relative (``unstructured/foo.pdf``) or legacy repo-root-relative
    (``demo/fixtures/unstructured/foo.pdf``); only the basename is used to derive
    the PDF filename, so both forms are handled transparently.
    """
    manifest_path = root / "manifest.json"
    dataset_id: str = root.name
    pdf_filename: str = _DEFAULT_PDF_FILENAME

    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning(
                "Could not read manifest at %s: %s. Using fallback dataset_id=%r and pdf_filename=%r.",
                manifest_path,
                exc,
                dataset_id,
                pdf_filename,
            )
            data = {}

        if isinstance(data, dict):
            candidate_id = data.get("dataset")
            if isinstance(candidate_id, str) and candidate_id:
                dataset_id = candidate_id

            for entry in data.get("provenance", []):
                if isinstance(entry, dict) and entry.get("kind") == "pdf":
                    path_str = entry.get("path", "")
                    basename = Path(path_str).name
                    if basename:
                        pdf_filename = basename
                        break

    return DatasetRoot(root=root, dataset_id=dataset_id, pdf_filename=pdf_filename)


def resolve_dataset_root(name: str | None = None) -> DatasetRoot:
    """Return the active :class:`DatasetRoot`.

    Resolution order:

    1. *name* argument (e.g. from ``--dataset`` CLI flag).
    2. ``FIXTURE_DATASET`` environment variable.
    3. Auto-discover the single dataset under :data:`DATASETS_CONTAINER_DIR`.
    4. Legacy fallback: treat :data:`FIXTURES_DIR` itself as the dataset root.

    Raises :class:`ValueError` when *name* is given but the corresponding
    directory does not exist under :data:`DATASETS_CONTAINER_DIR`, or when
    multiple datasets exist but none is selected.
    """
    effective_name: str | None = name or os.getenv("FIXTURE_DATASET")

    if effective_name:
        # Guard against path traversal: only plain directory names are allowed.
        if effective_name != Path(effective_name).name or not effective_name or "/" in effective_name or "\\" in effective_name:
            raise ValueError(
                f"Dataset name must be a simple directory name without path separators, got {effective_name!r}"
            )
        candidate = DATASETS_CONTAINER_DIR / effective_name
        if candidate.is_dir():
            return _load_dataset_root_from_dir(candidate)
        available = list_available_datasets()
        raise ValueError(
            f"Dataset {effective_name!r} not found under {DATASETS_CONTAINER_DIR}. "
            f"Available: {available}"
        )

    # Auto-discover when the container directory exists.
    if DATASETS_CONTAINER_DIR.is_dir():
        subdirs = [
            d
            for d in DATASETS_CONTAINER_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        if len(subdirs) == 1:
            return _load_dataset_root_from_dir(subdirs[0])
        if len(subdirs) > 1:
            raise ValueError(
                f"Multiple datasets found under {DATASETS_CONTAINER_DIR}: "
                f"{sorted(d.name for d in subdirs)}. "
                f"Select one with --dataset <name> or set FIXTURE_DATASET=<name>."
            )

    # Legacy fallback: FIXTURES_DIR itself acts as the dataset root.
    return _load_dataset_root_from_dir(FIXTURES_DIR)


def list_available_datasets() -> list[str]:
    """Return the names of all dataset directories under :data:`DATASETS_CONTAINER_DIR`."""
    if not DATASETS_CONTAINER_DIR.is_dir():
        return []
    return sorted(
        d.name
        for d in DATASETS_CONTAINER_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


__all__ = [
    "ARTIFACTS_DIR",
    "CONFIG_DIR",
    "DATASETS_CONTAINER_DIR",
    "DatasetRoot",
    "FIXTURES_DIR",
    "PDF_PIPELINE_CONFIG_PATH",
    "list_available_datasets",
    "resolve_dataset_root",
]
