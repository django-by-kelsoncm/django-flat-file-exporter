from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FlatFileExporterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "flat_file_exporter"
    verbose_name = _("Exports")
