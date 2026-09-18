from django import forms

from flat_file_exporter.forms import BaseExportForm, ExportColumn


class PeopleExportForm(BaseExportForm):
    """People list

    All the people, with optional filtering.

    @ignored line
    """

    url_name = "people_export"
    columns = [ExportColumn("name", "Full name"), ExportColumn("age")]

    min_age = forms.IntegerField(label="Minimum age", required=False, help_text="Only people at least this old")
