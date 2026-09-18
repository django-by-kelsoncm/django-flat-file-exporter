import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from flat_file_exporter import views
from flat_file_exporter.models import ExportedFile
from flat_file_exporter.views import BaseExportView
from tests.sampleapp.views import PeopleExportView

pytestmark = pytest.mark.django_db


# ---- index -----------------------------------------------------------------


def test_index_requires_login(client):
    assert client.get(reverse("flat_file_exporter:index")).status_code == 302


def test_index_requires_permission(client, db):
    client.force_login(get_user_model().objects.create_user("nobody", password="pw"))  # noqa: S106
    assert client.get(reverse("flat_file_exporter:index")).status_code == 403


def test_index_lists_own_exports_only(client_logged, export, other_user):
    foreign = ExportedFile.objects.create_export("k", "foreign.csv", "", "text/csv", other_user.id)
    response = client_logged.get(reverse("flat_file_exporter:index"))
    content = response.content.decode()
    assert response.status_code == 200
    assert export.name in content and foreign.name not in content
    assert "People list" in content  # catalog of forms
    assert "/people/" in content
    assert reverse("flat_file_exporter:task_status", args=[export.pk]) in content
    assert reverse("flat_file_exporter:delete", args=[export.pk]) in content


def test_index_visibility_all_shows_everything(client_logged, export, other_user):
    foreign = ExportedFile.objects.create_export("k", "foreign.csv", "", "text/csv", other_user.id)
    with override_settings(FLAT_FILE_EXPORTER_VISIBILITY="all"):
        content = client_logged.get(reverse("flat_file_exporter:index")).content.decode()
    assert export.name in content and foreign.name in content


def test_index_hides_trashed_and_shows_empty_state(client_logged, export):
    export.status = ExportedFile.Status.TRASHED
    export.save()
    content = client_logged.get(reverse("flat_file_exporter:index")).content.decode()
    assert export.name not in content
    assert "No exports found" in content


def test_index_uses_configured_base_template(client_logged, export):
    with override_settings(FLAT_FILE_EXPORTER_BASE_TEMPLATE="flat_file_exporter/base.html"):
        response = client_logged.get(reverse("flat_file_exporter:index"))
    assert "bootstrap" in response.content.decode()


# ---- status ----------------------------------------------------------------


def test_status_view_payload(client_logged, generated):
    generated.task_id = "abc"
    generated.failure_stack = "secret stack"
    generated.save()
    payload = client_logged.get(reverse("flat_file_exporter:task_status", args=[generated.pk])).json()
    assert payload["status"]["value"] == ExportedFile.Status.GENERATED
    assert payload["done"] is True
    assert payload["download_url"].endswith("/download/")
    assert payload["failure_stack"] is None  # only superusers see stack traces
    assert payload["celery_state"] is None  # no result backend configured: state is unknown, not an error


def test_status_view_reports_celery_state(client_logged, export, monkeypatch):
    class FakeResult:
        def __init__(self, task_id):
            self.state = "STARTED"

    monkeypatch.setattr(views, "AsyncResult", FakeResult)
    export.task_id = "abc"
    export.save()
    payload = client_logged.get(reverse("flat_file_exporter:task_status", args=[export.pk])).json()
    assert payload["celery_state"] == "STARTED"


def test_status_view_without_celery_installed(client_logged, export, monkeypatch):
    monkeypatch.setattr(views, "AsyncResult", None)
    export.task_id = "abc"
    export.save()
    payload = client_logged.get(reverse("flat_file_exporter:task_status", args=[export.pk])).json()
    assert payload["celery_state"] is None


def test_status_view_superuser_sees_stack(client, generated, db):
    admin = get_user_model().objects.create_superuser("root", password="pw")  # noqa: S106
    generated.failure_stack = "secret stack"
    generated.save()
    client.force_login(admin)
    # superuser is not a stakeholder, so visibility "all" is needed to reach the export
    with override_settings(FLAT_FILE_EXPORTER_VISIBILITY="all"):
        payload = client.get(reverse("flat_file_exporter:task_status", args=[generated.pk])).json()
    assert payload["failure_stack"] == "secret stack"


def test_status_view_pending_without_task(client_logged, export):
    payload = client_logged.get(reverse("flat_file_exporter:task_status", args=[export.pk])).json()
    assert payload["done"] is False and payload["celery_state"] is None


def test_status_view_hides_foreign_exports(client_logged, other_user):
    foreign = ExportedFile.objects.create_export("k", "f.csv", "", "text/csv", other_user.id)
    assert client_logged.get(reverse("flat_file_exporter:task_status", args=[foreign.pk])).status_code == 404


# ---- delete ----------------------------------------------------------------


def test_delete_requires_post(client_logged, export):
    response = client_logged.get(reverse("flat_file_exporter:delete", args=[export.pk]))
    assert response.status_code == 405


def test_delete_moves_to_trash(client_logged, export):
    response = client_logged.post(reverse("flat_file_exporter:delete", args=[export.pk]))
    export.refresh_from_db()
    assert response.status_code == 200 and response.json()["success"] is True
    assert response.json()["status"]["value"] == ExportedFile.Status.TRASHED
    assert export.status == ExportedFile.Status.TRASHED and export.trashed_at


def test_delete_forbidden_for_non_stakeholder(client_logged, other_user):
    foreign = ExportedFile.objects.create_export("k", "f.csv", "", "text/csv", other_user.id)
    assert client_logged.post(reverse("flat_file_exporter:delete", args=[foreign.pk])).status_code == 403
    foreign.refresh_from_db()
    assert foreign.status != ExportedFile.Status.TRASHED


# ---- download --------------------------------------------------------------


def test_download_streams_stored_file(client_logged, generated):
    response = client_logged.get(reverse("flat_file_exporter:download", args=[generated.pk]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"zipdata"
    assert "attachment" in response["Content-Disposition"] and generated.name in response["Content-Disposition"]
    assert response["Content-Type"] == "application/zip"


def test_download_forbidden_for_non_stakeholder(client, generated, other_user):
    client.force_login(other_user)
    assert client.get(reverse("flat_file_exporter:download", args=[generated.pk])).status_code == 403


def test_download_allows_added_stakeholder(client, generated, other_user, stakeholder_of):
    stakeholder_of(generated, other_user)
    client.force_login(other_user)
    assert client.get(reverse("flat_file_exporter:download", args=[generated.pk])).status_code == 200


def test_download_404_when_nothing_stored(client_logged, export):
    assert client_logged.get(reverse("flat_file_exporter:download", args=[export.pk])).status_code == 404


def test_download_requires_login(client, generated):
    assert client.get(reverse("flat_file_exporter:download", args=[generated.pk])).status_code == 302


# ---- BaseExportView --------------------------------------------------------


def test_export_view_get_renders_form(client_logged):
    response = client_logged.get(reverse("people_export"))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Minimum age" in content and "Information:" in content and "Show columns" in content
    assert 'data-format="csv"' in content


def test_export_view_requires_permission(client, db):
    client.force_login(get_user_model().objects.create_user("nobody", password="pw"))  # noqa: S106
    assert client.get(reverse("people_export")).status_code == 403


def test_export_view_post_creates_export_runs_task_and_redirects(client_logged, user):
    PeopleExportView.task_ref.calls.clear()
    response = client_logged.post(reverse("people_export"), {"filetype": "csv", "min_age": "30"})
    assert response.status_code == 302 and response.url == reverse("flat_file_exporter:index")
    export = ExportedFile.objects.get()
    assert export.kind == "people-export" and export.filetype == "csv"
    assert export.name.startswith("people-export-ada-") and export.name.endswith(".csv.zip")
    assert export.content_type == "application/zip"
    assert export.notes == "Requested by ada"
    assert export.task_id == "task-123"
    assert export.status == ExportedFile.Status.GENERATED  # the sample task runs inline
    assert export.stakeholders.get().user == user
    ((args, kwargs),) = PeopleExportView.task_ref.calls
    assert args == (export.pk,) and kwargs == {"filetype": "csv", "min_age": 30}


def test_export_view_post_invalid_form_rerenders(client_logged):
    response = client_logged.post(reverse("people_export"), {"filetype": "csv", "min_age": "not-a-number"})
    assert response.status_code == 200
    assert "Attention!" in response.content.decode()
    assert not ExportedFile.objects.exists()


def test_export_view_marks_failure_when_enqueue_fails(client_logged, monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("broker down")

    monkeypatch.setattr(PeopleExportView.task_ref, "delay", boom)
    with pytest.raises(ConnectionError):
        client_logged.post(reverse("people_export"), {"filetype": "csv"})
    export = ExportedFile.objects.get()
    assert export.status == ExportedFile.Status.FAILED and export.failure_cause == "broker down"


def test_export_view_requires_form_class_and_task():
    with pytest.raises(NotImplementedError):
        BaseExportView().get_form_class()
    with pytest.raises(NotImplementedError):
        BaseExportView().get_task()


def test_export_view_kind_and_defaults_can_be_overridden(rf, user):
    class Custom(PeopleExportView):
        kind = "custom-kind"
        notes = "custom notes"

    view = Custom()
    view.request = rf.get("/")
    view.request.user = user
    assert view.get_kind() == "custom-kind" and view.get_notes() == "custom notes"
    assert PeopleExportView().get_content_type() == "application/zip"

    assert BaseExportView().get_content_type() == "application/octet-stream"


def test_export_view_template_names_follow_the_form_module_path():
    names = PeopleExportView().get_template_names()
    assert names == ["tests/sampleapp/people_export.html", "flat_file_exporter/form.html"]
