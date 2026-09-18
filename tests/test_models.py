import pytest

from flat_file_exporter.models import ExportedFile, ExportStakeholder

pytestmark = pytest.mark.django_db


def test_create_export_registers_requester_as_stakeholder(export, user):
    assert export.status == ExportedFile.Status.REQUESTED
    assert export.validation_code
    stakeholder = export.stakeholders.get()
    assert stakeholder.user == user
    assert stakeholder.role == ExportStakeholder.Role.REQUESTER
    assert "ada" in str(stakeholder)
    assert "people.csv.zip" in str(export)


def test_validation_code_is_unique_and_kept_on_update(export, user):
    other = ExportedFile.objects.create_export("k", "n.csv", "", "text/csv", user.id)
    code = export.validation_code
    export.notes = "changed"
    export.save()
    export.refresh_from_db()
    assert export.validation_code == code != other.validation_code


def test_lifecycle_full_success(export):
    lifecycle = export.lifecycle
    lifecycle.requested()
    lifecycle.rendering()
    assert export.status == ExportedFile.Status.GENERATING and export.generation_started_at
    lifecycle.rendered(1234)
    assert export.size == 1234 and export.generation_finished_at and export.processing_time >= 0
    lifecycle.uploading()
    lifecycle.uploaded("some/key.zip")
    assert export.storage_key == "some/key.zip" and export.upload_time >= 0
    lifecycle.succeeded()
    export.refresh_from_db()
    assert export.status == ExportedFile.Status.GENERATED
    assert export.download_url.endswith(f"/{export.pk}/download/")


def test_lifecycle_failed_records_cause_and_stack(export):
    try:
        raise ValueError("boom")
    except ValueError as error:
        export.lifecycle.failed(error)
    export.refresh_from_db()
    assert export.status == ExportedFile.Status.FAILED
    assert export.failure_cause == "boom"
    assert "ValueError" in export.failure_stack
    assert export.failed_at


def test_lifecycle_failed_without_exception(export):
    export.lifecycle.failed()
    assert export.failure_cause == "Failure while generating the file"
    assert export.failure_stack == "No stack trace available"


def test_status_metadata():
    status = ExportedFile.Status.GENERATED
    assert status.color == "success" and status.icon and status.short_display == "Generated"
    assert set(status.as_dict()) == {"value", "display", "short_display", "icon", "color"}


def test_status_helpers_on_instance(export):
    assert export.status_display is ExportedFile.Status.REQUESTED
    assert export.status_icon == "fas fa-inbox"
    assert export.file_name == export.name


def test_open_and_content_read_from_storage(generated):
    assert generated.file_content == b"zipdata"
    with generated.open() as stored:
        assert stored.read() == b"zipdata"


def test_open_without_stored_file_raises(export):
    assert export.download_url is None
    with pytest.raises(FileNotFoundError):
        export.open()
