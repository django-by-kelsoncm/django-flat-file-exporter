from flat_file_exporter.views import BaseExportView
from tests.sampleapp.forms import PeopleExportForm
from tests.sampleapp.tasks import ImmediateTask, people_export


class PeopleExportView(BaseExportView):
    permission_required = "flat_file_exporter.view_exportedfile"
    form_class = PeopleExportForm
    task_ref = ImmediateTask(people_export)
    content_type_export = "application/zip"
