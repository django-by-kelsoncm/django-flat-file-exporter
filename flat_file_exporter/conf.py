"""Runtime settings for flat_file_exporter, all overridable in the Django settings module."""

from copy import deepcopy
from typing import Any

from django.conf import settings
from django.core.files.storage import Storage, storages

DEFAULT_FILETYPES: dict[str, dict[str, str]] = {
    "xlsx": {
        "class": "flat_file_renderers.xlsx.XlsxRenderer",
        "label": "Excel (.xlsx)",
        "hint": "Excel workbook (limited to 1,048,576 rows)",
        "icon": "fas fa-file-excel text-success",
    },
    "csv": {
        "class": "flat_file_renderers.separated_value.CsvRenderer",
        "label": "CSV (.csv)",
        "hint": "Comma-separated values",
        "icon": "fas fa-file-csv text-primary",
    },
    "tsv": {
        "class": "flat_file_renderers.separated_value.TsvRenderer",
        "label": "TSV (.tsv)",
        "hint": "Tab-separated values",
        "icon": "fas fa-file-csv text-primary",
    },
    "json": {
        "class": "flat_file_renderers.json.JsonRenderer",
        "label": "JSON (.json)",
        "hint": "JSON file",
        "icon": "fas fa-file-code text-warning",
    },
    "html": {
        "class": "flat_file_renderers.html.HtmlRenderer",
        "label": "HTML (.html)",
        "hint": "HTML table",
        "icon": "fas fa-file-code text-orange",
    },
    "parquet": {
        "class": "flat_file_renderers.parquet.ParquetRenderer",
        "label": "Parquet (.parquet)",
        "hint": "High-performance columnar file (Apache Parquet)",
        "icon": "fas fa-database text-info",
    },
}

VISIBILITY_OWN = "own"
VISIBILITY_ALL = "all"


def get_filetypes() -> dict[str, dict[str, str]]:
    """Return the filetype -> renderer map: the defaults updated by ``FLAT_FILE_EXPORTER_FILETYPES``.

    Entries in the setting replace the default entry with the same key; a value of ``None`` removes it.
    """
    filetypes = deepcopy(DEFAULT_FILETYPES)
    for key, value in getattr(settings, "FLAT_FILE_EXPORTER_FILETYPES", {}).items():
        if value is None:
            filetypes.pop(key, None)
        else:
            filetypes[key] = value
    return filetypes


def get_storage() -> Storage:
    """Return the Django storage used for generated files (``FLAT_FILE_EXPORTER_STORAGE_ALIAS``, default "default")."""
    return storages[getattr(settings, "FLAT_FILE_EXPORTER_STORAGE_ALIAS", "default")]


def get_upload_prefix() -> str:
    """Directory prefix inside the storage for generated files (``FLAT_FILE_EXPORTER_UPLOAD_PREFIX``)."""
    return getattr(settings, "FLAT_FILE_EXPORTER_UPLOAD_PREFIX", "flat_file_exporter")


def get_base_template() -> str:
    """Template the package pages extend (``FLAT_FILE_EXPORTER_BASE_TEMPLATE``)."""
    return getattr(settings, "FLAT_FILE_EXPORTER_BASE_TEMPLATE", "flat_file_exporter/base.html")


def get_visibility() -> str:
    """``"own"`` (default): users see only exports they are a stakeholder of; ``"all"``: every export."""
    return getattr(settings, "FLAT_FILE_EXPORTER_VISIBILITY", VISIBILITY_OWN)


def get_setting(name: str, default: Any = None) -> Any:
    return getattr(settings, f"FLAT_FILE_EXPORTER_{name}", default)
