import logging
import traceback
import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from flat_file_exporter.conf import get_storage

logger = logging.getLogger(__name__)

_STATUS_META: dict[int, dict[str, str]] = {
    0: {"short_display": _("Requested"), "icon": "fas fa-inbox", "color": "secondary"},
    1: {"short_display": _("Generating"), "icon": "far fa-file", "color": "warning"},
    5: {"short_display": _("Generated"), "icon": "far fa-file-alt", "color": "success"},
    9: {"short_display": _("Failed"), "icon": "fas fa-exclamation-circle", "color": "danger"},
    10: {"short_display": _("Trashed"), "icon": "far fa-trash-alt", "color": "danger"},
}


class ExportedFile(models.Model):
    """A requested export: its lifecycle, timings, failure details and where the generated file is stored."""

    class Status(models.IntegerChoices):
        REQUESTED = 0, _("Waiting to start")
        GENERATING = 1, _("Generating the file")
        GENERATED = 5, _("File generated")
        FAILED = 9, _("File generation failed")
        TRASHED = 10, _("File in the trash")

        @property
        def short_display(self) -> str:
            return str(_STATUS_META[self.value]["short_display"])

        @property
        def icon(self) -> str:
            return _STATUS_META[self.value]["icon"]

        @property
        def color(self) -> str:
            return _STATUS_META[self.value]["color"]

        def as_dict(self) -> dict[str, Any]:
            return {
                "value": self.value,
                "display": str(self.label),
                "short_display": self.short_display,
                "icon": self.icon,
                "color": self.color,
            }

    class Lifecycle:
        """Records each step of the export on the model (status, timings, failure details)."""

        def __init__(self, exported_file: "ExportedFile"):
            self.exported_file = exported_file
            self.upload_started_at = None

        def requested(self) -> None:
            pass

        def rendering(self) -> None:
            self.exported_file.status = ExportedFile.Status.GENERATING
            self.exported_file.generation_started_at = now()
            self.exported_file.save()

        def rendered(self, file_length: int) -> None:
            exported_file = self.exported_file
            exported_file.size = file_length
            exported_file.generation_finished_at = now()
            exported_file.processing_time = int(
                (exported_file.generation_finished_at - exported_file.generation_started_at).total_seconds()
            )
            exported_file.save()

        def uploading(self) -> None:
            self.upload_started_at = now()
            self.exported_file.save()

        def uploaded(self, storage_key: str) -> None:
            self.exported_file.storage_key = storage_key
            self.exported_file.upload_time = int((now() - self.upload_started_at).total_seconds())
            self.exported_file.save()

        def succeeded(self) -> None:
            self.exported_file.status = ExportedFile.Status.GENERATED
            self.exported_file.save()

        def failed(self, error: Exception | None = None) -> None:
            exported_file = self.exported_file
            logger.error("Failed to generate export %s: %s", exported_file, error)
            exported_file.status = ExportedFile.Status.FAILED
            exported_file.failure_cause = (
                str(error) if error is not None else gettext("Failure while generating the file")
            )
            exported_file.failure_stack = (
                traceback.format_exc() if error is not None else gettext("No stack trace available")
            )
            exported_file.failed_at = now()
            exported_file.save()

    class ExportedFileManager(models.Manager):
        def create_export(
            self, kind: str, name: str, notes: str, content_type: str, requester_id: int, **kwargs: Any
        ) -> "ExportedFile":
            """Create an export in the REQUESTED status and register the requester as its first stakeholder."""
            exported_file = self.create(
                status=ExportedFile.Status.REQUESTED,
                kind=kind,
                name=name,
                notes=notes,
                content_type=content_type,
                **kwargs,
            )
            ExportStakeholder.objects.create(
                user_id=requester_id, exported_file=exported_file, role=ExportStakeholder.Role.REQUESTER
            )
            return exported_file

    status = models.SmallIntegerField(_("status"), choices=Status.choices, default=Status.REQUESTED)
    requested_at = models.DateTimeField(_("requested at"), auto_now_add=True)
    generation_started_at = models.DateTimeField(_("generation started at"), null=True, blank=True)
    generation_finished_at = models.DateTimeField(_("generation finished at"), null=True, blank=True)
    failed_at = models.DateTimeField(_("failed at"), null=True, blank=True)
    trashed_at = models.DateTimeField(_("trashed at"), null=True, blank=True)
    kind = models.CharField(_("kind of export"), max_length=255)
    name = models.CharField(_("file name"), max_length=255)
    notes = models.TextField(_("notes"), null=True, blank=True)
    validation_code = models.CharField(_("validation code"), max_length=64, unique=True, editable=False)
    storage_key = models.CharField(_("storage key"), max_length=1024, blank=True, default="")
    content_type = models.CharField(_("content type"), max_length=255, default="application/octet-stream")
    size = models.BigIntegerField(_("size (bytes)"), default=0)
    processing_time = models.IntegerField(_("processing time (seconds)"), default=0)
    upload_time = models.IntegerField(_("upload time (seconds)"), default=0)
    task_id = models.CharField(_("task id"), max_length=255, null=True, blank=True, db_index=True)
    failure_cause = models.TextField(_("failure cause"), null=True, blank=True)
    failure_stack = models.TextField(_("failure stack"), null=True, blank=True)
    filetype = models.CharField(_("file format"), max_length=50, null=True, blank=True)

    objects = ExportedFileManager()

    class Meta:
        verbose_name = _("exported file")
        verbose_name_plural = _("exported files")
        ordering = ["-requested_at"]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.lifecycle = ExportedFile.Lifecycle(self)

    def __str__(self) -> str:
        return f"{self.name} @ {self.requested_at}"

    @property
    def status_display(self) -> "ExportedFile.Status":
        return ExportedFile.Status(self.status)

    @property
    def status_icon(self) -> str:
        return self.status_display.icon

    @property
    def file_name(self) -> str:
        return self.name

    def open(self):
        """Open the stored file for reading through the configured Django storage."""
        if not self.storage_key:
            raise FileNotFoundError("This export has no stored file yet.")
        return get_storage().open(self.storage_key, "rb")

    @property
    def file_content(self) -> bytes:
        with self.open() as stored:
            return stored.read()

    @property
    def download_url(self) -> str | None:
        if self.storage_key:
            return reverse("flat_file_exporter:download", kwargs={"pk": self.pk})
        return None

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is None and not self.validation_code:
            self.validation_code = uuid.uuid4().hex
        super().save(*args, **kwargs)


class ExportStakeholder(models.Model):
    """A user with an interest in an export; only stakeholders can see, download or trash it (see visibility)."""

    class Role(models.IntegerChoices):
        REQUESTER = 1, _("Requester")
        RECIPIENT = 2, _("Recipient")
        MANAGER = 3, _("Manager")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, verbose_name=_("user"))
    exported_file = models.ForeignKey(
        ExportedFile, models.PROTECT, related_name="stakeholders", verbose_name=_("exported file")
    )
    role = models.SmallIntegerField(_("role"), choices=Role.choices)
    assigned_at = models.DateTimeField(_("assigned at"), auto_now_add=True)

    class Meta:
        verbose_name = _("stakeholder")
        verbose_name_plural = _("stakeholders")

    def __str__(self) -> str:
        return f"{self.user} on '{self.exported_file}' as '{self.get_role_display()}'"
