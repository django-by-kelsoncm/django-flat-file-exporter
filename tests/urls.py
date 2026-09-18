from django.contrib import admin
from django.urls import include, path

from tests.sampleapp.views import PeopleExportView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("exports/", include("flat_file_exporter.urls")),
    path("people/", PeopleExportView.as_view(), name="people_export"),
]
