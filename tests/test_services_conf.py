import zipfile

import pytest
from django.test import override_settings

from flat_file_exporter import conf
from flat_file_exporter.conf import get_storage
from flat_file_exporter.models import ExportedFile
from flat_file_exporter.services import BaseExportService
from tests.sampleapp.tasks import PeopleService

pytestmark = pytest.mark.django_db


def test_render_generates_uploads_and_records_lifecycle(export):
    PeopleService(export, "csv").render()
    export.refresh_from_db()
    assert export.status == ExportedFile.Status.GENERATED
    assert export.size > 0
    assert export.storage_key.startswith("flat_file_exporter/people.csv")
    with get_storage().open(export.storage_key, "rb") as stored, zipfile.ZipFile(stored) as archive:
        content = archive.read(archive.namelist()[0]).decode()
    assert "Ada" in content and "Alan" in content


def test_same_name_twice_does_not_overwrite_and_key_is_recorded(export, user):
    twin = ExportedFile.objects.create_export("people", export.name, "", "application/zip", user.id)
    PeopleService(export, "csv").render()
    PeopleService(twin, "csv").render()
    assert export.storage_key != twin.storage_key
    assert get_storage().exists(export.storage_key) and get_storage().exists(twin.storage_key)


def test_render_uses_upload_prefix_setting(export):
    with override_settings(FLAT_FILE_EXPORTER_UPLOAD_PREFIX="custom/dir"):
        PeopleService(export, "json").render()
    assert export.storage_key.startswith("custom/dir/")


def test_upload_prefix_can_be_overridden_by_attribute(export):
    service = PeopleService(export, "csv")
    service.upload_prefix = "attr"
    service.render()
    assert export.storage_key.startswith("attr/")


def test_render_marks_failure_and_reraises(export):
    class Broken(BaseExportService):
        def get_dataset(self):
            raise RuntimeError("no data")

    with pytest.raises(RuntimeError, match="no data"):
        Broken(export, "csv").render()
    export.refresh_from_db()
    assert export.status == ExportedFile.Status.FAILED
    assert export.failure_cause == "no data"


def test_unknown_filetype_is_rejected(export):
    with pytest.raises(NotImplementedError, match="nope"):
        PeopleService(export, "nope").get_renderer_class()


def test_unimportable_renderer_is_reported(export):
    with override_settings(FLAT_FILE_EXPORTER_FILETYPES={"bad": {"class": "no_such_module.Renderer"}}):
        with pytest.raises(ImportError, match="no_such_module.Renderer"):
            PeopleService(export, "bad").get_renderer_class()


def test_get_dataset_must_be_implemented(export):
    with pytest.raises(NotImplementedError):
        BaseExportService(export, "csv").get_dataset()


def test_upload_without_rendered_file_fails(export):
    with pytest.raises(ValueError):
        PeopleService(export, "csv").do_upload()


def test_filetypes_setting_overrides_and_removes():
    custom = {"csv": None, "txt": {"class": "flat_file_renderers.text.TextRenderer", "label": "Text"}}
    with override_settings(FLAT_FILE_EXPORTER_FILETYPES=custom):
        filetypes = conf.get_filetypes()
    assert "csv" not in filetypes and "txt" in filetypes and "xlsx" in filetypes
    assert "csv" in conf.get_filetypes()


def test_conf_defaults_and_overrides():
    assert conf.get_upload_prefix() == "flat_file_exporter"
    assert conf.get_base_template() == "flat_file_exporter/base.html"
    assert conf.get_visibility() == conf.VISIBILITY_OWN
    assert conf.get_setting("MISSING", 7) == 7
    with override_settings(
        FLAT_FILE_EXPORTER_BASE_TEMPLATE="x.html",
        FLAT_FILE_EXPORTER_VISIBILITY="all",
        FLAT_FILE_EXPORTER_STORAGE_ALIAS="default",
    ):
        assert conf.get_base_template() == "x.html"
        assert conf.get_visibility() == conf.VISIBILITY_ALL
        assert conf.get_storage() is not None
