# django-flat-file-exporter

Reusable Django app to **request, generate asynchronously, store and download flat-file exports**
(xlsx, csv, tsv, json, html, parquet). It builds on
[flat-file-renderers](https://github.com/python-by-kelsoncm/python-flat-file-renderers) for the file generation
and on Django's [storage API](https://docs.djangoproject.com/en/stable/ref/files/storage/) for keeping the results,
so files can live on disk, S3, Google Drive... whatever storage backend you configure.

What you get:

- `ExportedFile` / `ExportStakeholder` models tracking each export: status, timings, failure cause and stack,
  storage key, who requested it and who else has access.
- `BaseExportForm`: declare the filters of an export as a normal Django form. Title, description (Markdown) and
  filter/column catalog are taken from the docstring and the form fields.
- `BaseExportView`: GET renders the form, POST validates it, registers the export and enqueues your task.
- `BaseExportService`: renders the dataset with the chosen renderer, uploads to the storage and records every step.
- A ready-made UI (catalog, list with live status polling, download, trash) and Django admin.

## Install

```shell
pip install "django-flat-file-exporter[all]"   # [all] = xlsx + parquet renderers and Celery
```

Requires Python 3.10+ and Django 5.2+. Celery is optional: any object with a `delay(exported_file_id, **data)`
method works as the task.

## Setup

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "django.contrib.humanize",
    "flat_file_exporter",
]

# urls.py
urlpatterns = [
    path("exports/", include("flat_file_exporter.urls")),
]
```

```shell
python manage.py migrate
```

Grant users the `flat_file_exporter.view_exportedfile` permission to let them use the pages.

## Declare an export

```python
# people/forms.py  (forms are discovered in the `forms` module of every installed app)
from django import forms
from flat_file_exporter.forms import BaseExportForm, ExportColumn


class PeopleExportForm(BaseExportForm):
    """People list

    All the people, optionally filtered by age. Markdown is supported here.
    """

    url_name = "people:export"  # URL name of the view below
    columns = [ExportColumn("name", "Full name"), ExportColumn("age")]

    min_age = forms.IntegerField(label="Minimum age", required=False)
```

```python
# people/tasks.py
from celery import shared_task
from flat_file_exporter.models import ExportedFile
from flat_file_exporter.services import BaseExportService


class PeopleService(BaseExportService):
    def get_dataset(self):  # a list of dicts, a dict, or a QuerySet
        return list(Person.objects.values("name", "age"))


@shared_task
def people_export(exported_file_id, filetype="csv", **filters):
    PeopleService(ExportedFile.objects.get(pk=exported_file_id), filetype).render()
```

```python
# people/views.py and urls.py
from flat_file_exporter.views import BaseExportView


class PeopleExportView(BaseExportView):
    permission_required = "flat_file_exporter.view_exportedfile"
    form_class = PeopleExportForm
    task_ref = people_export
    content_type_export = "application/zip"


urlpatterns = [path("export/", PeopleExportView.as_view(), name="export")]  # app_name = "people"
```

The export now appears in the catalog at `/exports/`. The user picks a format in the form, the task runs in the
background, and the list page polls the status until the file can be downloaded.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `FLAT_FILE_EXPORTER_STORAGE_ALIAS` | `"default"` | Alias in `STORAGES` used to save the generated files |
| `FLAT_FILE_EXPORTER_UPLOAD_PREFIX` | `"flat_file_exporter"` | Directory inside the storage |
| `FLAT_FILE_EXPORTER_FILETYPES` | see `conf.DEFAULT_FILETYPES` | Filetype to renderer map; entries replace the defaults, `None` removes one |
| `FLAT_FILE_EXPORTER_BASE_TEMPLATE` | `"flat_file_exporter/base.html"` | Layout the pages extend |
| `FLAT_FILE_EXPORTER_VISIBILITY` | `"own"` | `"own"`: users see only exports they are a stakeholder of; `"all"`: every export |

The bundled base layout loads Bootstrap 4, jQuery and Font Awesome 5 from CDNs. To use your own layout (for example
AdminLTE 3), point `FLAT_FILE_EXPORTER_BASE_TEMPLATE` at a template that provides the blocks `extra_styles`,
`content` and `bottom_scripts`, with jQuery and Bootstrap 4 loaded.

## Translations

All texts are translatable (`gettext`), with English as the source language. A `pt_BR` catalog is included; the
language follows Django's active language (`LANGUAGE_CODE` / `LocaleMiddleware`). The strings used by the bundled
JavaScript are delivered by the list page as `window.flatFileExporterI18n`.

To add a language, run `django-admin makemessages -l <code>` inside the `flat_file_exporter` directory, translate
`locale/<code>/LC_MESSAGES/django.po` and run `django-admin compilemessages`. Note that the `{% trans %}` tag doubles
`%` when looking a message up, so msgids that contain `%s` in the templates are `%%s` in the catalog.

## Security notes

- Downloading and trashing an export requires being one of its stakeholders (the requester is added automatically).
- The failure stack trace is only returned by the status endpoint to superusers.
- Generated files are read through the storage API; make sure the storage you configure is not publicly readable.

## Development

```shell
uv venv && uv pip install -e ".[dev]"
pytest --cov
ruff check . && ruff format --check .
```

## License

MIT
