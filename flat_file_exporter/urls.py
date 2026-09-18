from django.urls import path

from flat_file_exporter import views

app_name = "flat_file_exporter"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("<int:pk>/status/", views.task_status_view, name="task_status"),
    path("<int:pk>/delete/", views.delete_view, name="delete"),
    path("<int:pk>/download/", views.DownloadView.as_view(), name="download"),
]
