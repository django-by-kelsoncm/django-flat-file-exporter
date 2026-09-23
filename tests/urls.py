from django.contrib import admin
from django.urls import include, path

from tests.sampleapp.views import PeopleExportView, RestrictedExportView

# Registered under the sampleapp AppConfig's dotted `name` ("tests.sampleapp"), not its auto-derived short
# `label` ("sampleapp") -- mirrors projects that namespace `include()` with `app_name = SomeConfig.name`, and
# exercises the `app_config.name` fallback in `BaseExportForm.get_default_link()`.
app_name_only_urls = ([path("export/", PeopleExportView.as_view(), name="app_name_only_export")], "tests.sampleapp")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("exports/", include("flat_file_exporter.urls")),
    path("people/", PeopleExportView.as_view(), name="people_export"),
    path("restricted/", RestrictedExportView.as_view(), name="restricted_export"),
    path("appname/", include(app_name_only_urls, namespace="tests.sampleapp")),
]
