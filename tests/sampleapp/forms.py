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


class RestrictedExportForm(BaseExportForm):
    """Restricted export

    Only visible in the catalog to users who also hold the delete permission.
    """

    url_name = "restricted_export"


class AppNameOnlyExportForm(BaseExportForm):
    """App name only export

    No ``url_name``; only resolvable by guessing the app's dotted ``name`` ("tests.sampleapp"), not its short
    ``label`` ("sampleapp") -- see ``tests.urls.app_name_only_urls``.
    """
