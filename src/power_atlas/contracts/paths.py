from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from power_atlas.settings import AppSettings

# Centralized filesystem locations for the demo.
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "demo"
FIXTURES_DIR = BASE_DIR / "fixtures"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
CONFIG_DIR = BASE_DIR / "config"
PDF_PIPELINE_CONFIG_PATH = CONFIG_DIR / "pdf_simple_kg_pipeline.yaml"

# Container directory that holds all named dataset roots.
DATASETS_CONTAINER_DIR = FIXTURES_DIR / "datasets"

_logger = logging.getLogger(__name__)

_DEFAULT_PDF_FILENAME = "chain_of_custody.pdf"


class AmbiguousDatasetError(ValueError):
    """Raised when multiple datasets exist but none has been explicitly selected.

    Callers that want to suppress *only* this ambiguity (e.g. the citation
    fallback in ``retrieval_and_qa``) should catch :exc:`AmbiguousDatasetError`
    specifically rather than relying on string-matching against the message.
    """


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


def resolve_dataset_root(
    name: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> DatasetRoot:
    """Return the active :class:`DatasetRoot`.

    Resolution order:

    1. *name* argument (e.g. from ``--dataset`` CLI flag).
    2. Package settings dataset selection (``POWER_ATLAS_DATASET`` then ``FIXTURE_DATASET``).
    3. Auto-discover the single dataset under :data:`DATASETS_CONTAINER_DIR`.
    4. Legacy fallback: treat :data:`FIXTURES_DIR` itself as the dataset root
       (only when :data:`DATASETS_CONTAINER_DIR` does not exist at all).

    Raises :class:`ValueError` when:

    * *name* is given but the corresponding directory does not exist under
      :data:`DATASETS_CONTAINER_DIR`.
    * Multiple datasets exist but none is explicitly selected.
    * :data:`DATASETS_CONTAINER_DIR` exists but contains no dataset
      subdirectories (empty container signals misconfiguration rather than a
      clean legacy layout).
    """
    effective_name: str | None = name or AppSettings.from_env(environ).dataset_name

    if effective_name:
        if (
            not effective_name
            or effective_name in (".", "..")
            or Path(effective_name).name != effective_name
        ):
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

    if DATASETS_CONTAINER_DIR.is_dir():
        subdirs = [
            d
            for d in DATASETS_CONTAINER_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        if len(subdirs) == 1:
            return _load_dataset_root_from_dir(subdirs[0])
        if len(subdirs) > 1:
            raise AmbiguousDatasetError(
                f"Multiple datasets found under {DATASETS_CONTAINER_DIR}: "
                f"{sorted(d.name for d in subdirs)}. "
                f"Select one with --dataset <name> or set FIXTURE_DATASET=<name>."
            )
        raise ValueError(
            f"No dataset directories found under {DATASETS_CONTAINER_DIR}. "
            f"Create a dataset subdirectory (e.g. demo_dataset_v1/) or remove "
            f"{DATASETS_CONTAINER_DIR} entirely to use the legacy fixture layout."
        )

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
    "AmbiguousDatasetError",
    "ARTIFACTS_DIR",
    "CONFIG_DIR",
    "DATASETS_CONTAINER_DIR",
    "DatasetRoot",
    "FIXTURES_DIR",
    "PDF_PIPELINE_CONFIG_PATH",
    "list_available_datasets",
    "resolve_dataset_root",
]