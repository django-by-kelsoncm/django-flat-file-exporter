from flat_file_exporter.models import ExportedFile
from flat_file_exporter.services import BaseExportService


class PeopleService(BaseExportService):
    def get_dataset(self):
        return [{"name": "Ada", "age": 36}, {"name": "Alan", "age": 41}]


def people_export(exported_file_id: int, filetype: str = "csv", **filters) -> None:
    PeopleService(ExportedFile.objects.get(pk=exported_file_id), filetype).render()


class ImmediateTask:
    """Stands in for a Celery task: ``delay`` runs the function inline and returns an object with an ``id``."""

    def __init__(self, function):
        self.function = function
        self.calls = []

    def delay(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.function(*args, **kwargs)
        return type("Result", (), {"id": "task-123"})()
