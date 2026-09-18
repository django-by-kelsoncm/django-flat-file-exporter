import importlib
import posixpath
from pathlib import Path
from typing import Any

from django.core.files import File
from django.db.models.query import QuerySet
from flat_file_renderers.base import BaseRenderer

from flat_file_exporter.conf import get_filetypes, get_storage, get_upload_prefix
from flat_file_exporter.models import ExportedFile


class BaseExportService:
    """Generates an export file with a renderer and stores it with the configured Django storage.

    Subclasses must implement :meth:`get_dataset` and may override :meth:`get_renderer_context`,
    :meth:`get_renderer` and :meth:`get_upload_prefix`. A typical Celery task is::

        @shared_task
        def my_export(exported_file_id, filetype="csv", **filters):
            exported_file = ExportedFile.objects.get(pk=exported_file_id)
            MyExportService(exported_file, filetype).render()
    """

    def __init__(self, exported_file: ExportedFile, filetype: str) -> None:
        self.exported_file = exported_file
        self.filetype = filetype
        self.file_content: Path | None = None
        self.uploaded_key: str | None = None

    def get_renderer_class(self) -> type[BaseRenderer]:
        renderer_path = get_filetypes().get(self.filetype, {}).get("class")
        if not renderer_path:
            raise NotImplementedError(f"No renderer mapped for filetype '{self.filetype}'")
        module_name, class_name = renderer_path.rsplit(".", 1)
        try:
            return getattr(importlib.import_module(module_name), class_name)
        except (ImportError, AttributeError) as error:
            raise ImportError(f"Renderer '{renderer_path}' could not be imported: {error}") from error

    def get_renderer_context(self) -> dict[str, Any]:
        """Extra context handed to the renderer constructor."""
        return {}

    def get_renderer(self) -> BaseRenderer:
        return self.get_renderer_class()(self.get_renderer_context())

    def get_upload_prefix(self) -> str:
        """Directory inside the storage where the file is saved (default: ``FLAT_FILE_EXPORTER_UPLOAD_PREFIX``)."""
        return getattr(self, "upload_prefix", get_upload_prefix())

    def get_dataset(self) -> QuerySet | dict | list | None:
        raise NotImplementedError("Subclasses must override get_dataset")

    def do_render(self, *args: Any, **kwargs: Any) -> None:
        self.file_content = self.get_renderer().render({"dataset": self.get_dataset()}, *args, **kwargs)

    def do_upload(self) -> str:
        if self.file_content is None:
            raise ValueError("No generated file to upload.")
        name = posixpath.join(self.get_upload_prefix(), self.exported_file.name)
        with self.file_content.open("rb") as handle:
            self.uploaded_key = get_storage().save(name, File(handle))
        return self.uploaded_key

    def render(self, *args: Any, **kwargs: Any) -> None:
        """Render, upload and record every step on the ExportedFile; on error it is marked FAILED and re-raised."""
        lifecycle = self.exported_file.lifecycle
        try:
            lifecycle.rendering()
            self.do_render(*args, **kwargs)
            lifecycle.rendered(self.file_content.stat().st_size)

            lifecycle.uploading()
            lifecycle.uploaded(self.do_upload())

            lifecycle.succeeded()
        except Exception as error:
            lifecycle.failed(error)
            raise
