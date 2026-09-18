import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import QuerySet
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView, TemplateView

from flat_file_exporter.conf import VISIBILITY_ALL, get_base_template, get_visibility
from flat_file_exporter.forms import BaseExportForm, to_snake_case
from flat_file_exporter.models import ExportedFile

try:
    from celery.result import AsyncResult
except ImportError:  # pragma: no cover - celery is an optional dependency
    AsyncResult = None

logger = logging.getLogger(__name__)

FINISHED_STATUSES = (ExportedFile.Status.GENERATED, ExportedFile.Status.FAILED, ExportedFile.Status.TRASHED)


def visible_exports(user) -> QuerySet[ExportedFile]:
    """Exports the user may see: all of them if ``FLAT_FILE_EXPORTER_VISIBILITY`` is "all", else only their own."""
    queryset = ExportedFile.objects.all()
    if get_visibility() == VISIBILITY_ALL:
        return queryset
    return queryset.filter(stakeholders__user=user).distinct()


def _celery_state(task_id: str | None) -> str | None:
    """Celery state of the task, or None when there is no task, Celery is missing or no result backend is set."""
    if not task_id or AsyncResult is None:
        return None
    try:
        return AsyncResult(task_id).state
    except Exception:  # noqa: BLE001 - a broken/absent result backend must not break the status endpoint
        logger.warning("Could not read the Celery state of task %s", task_id, exc_info=True)
        return None


@login_required
@permission_required("flat_file_exporter.view_exportedfile", raise_exception=True)
def task_status_view(request: HttpRequest, pk: int) -> JsonResponse:
    """Polling endpoint: current status, timings and failure details of an export."""
    exported_file = get_object_or_404(visible_exports(request.user), pk=pk)
    celery_state = _celery_state(exported_file.task_id)

    def iso(value):
        return value.isoformat() if value else None

    return JsonResponse(
        {
            "id": exported_file.id,
            "task_id": exported_file.task_id,
            "status": exported_file.status_display.as_dict(),
            "celery_state": celery_state,
            "done": exported_file.status in FINISHED_STATUSES,
            "size": exported_file.size,
            "storage_key": exported_file.storage_key,
            "generation_finished_at": iso(exported_file.generation_finished_at),
            "processing_time": exported_file.processing_time,
            "upload_time": exported_file.upload_time,
            "failed_at": iso(exported_file.failed_at),
            "trashed_at": iso(exported_file.trashed_at),
            "failure_cause": exported_file.failure_cause,
            "failure_stack": exported_file.failure_stack if request.user.is_superuser else None,
            "download_url": exported_file.download_url,
        }
    )


@login_required
@permission_required("flat_file_exporter.view_exportedfile", raise_exception=True)
def delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Move an export to the trash (status TRASHED). POST only."""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": _("Method not allowed")}, status=405)

    exported_file = get_object_or_404(ExportedFile, pk=pk)
    if not exported_file.stakeholders.filter(user=request.user).exists():
        return HttpResponseForbidden()

    exported_file.status = ExportedFile.Status.TRASHED
    exported_file.trashed_at = now()
    exported_file.save()
    logger.info("Export %s moved to the trash by %s", pk, request.user.get_username())
    return JsonResponse(
        {
            "success": True,
            "message": _("File moved to the trash"),
            "id": exported_file.id,
            "status": exported_file.status_display.as_dict(),
        }
    )


class IndexView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Catalog of the available export forms plus the paginated list of the user's exports."""

    permission_required = "flat_file_exporter.view_exportedfile"
    model = ExportedFile
    template_name = "flat_file_exporter/index.html"
    context_object_name = "exported_files"
    paginate_by = 12

    def get_queryset(self):
        return visible_exports(self.request.user).exclude(status=ExportedFile.Status.TRASHED)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["base_template"] = get_base_template()
        context["forms"] = BaseExportForm.get_export_forms()
        context["statuses"] = BaseExportForm.get_statuses()
        context["status"] = ExportedFile.Status
        return context


class DownloadView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        exported_file = get_object_or_404(ExportedFile, pk=pk)
        if not exported_file.stakeholders.filter(user=request.user).exists():
            return HttpResponseForbidden()
        if not exported_file.storage_key:
            return HttpResponse(status=404)
        return FileResponse(
            exported_file.open(),
            as_attachment=True,
            filename=exported_file.name,
            content_type=exported_file.content_type,
        )


class BaseExportView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Base view of an export: GET renders the form, POST validates it, registers the export and enqueues the task.

    Subclasses define ``form_class`` (a :class:`BaseExportForm`), ``task_ref`` (a Celery task, or anything with a
    ``delay(exported_file_id, **cleaned_data)`` method) and ``permission_required``; optionally ``kind``,
    ``content_type_export`` and ``notes``, or override the matching ``get_*`` methods.
    """

    template_name = "flat_file_exporter/form.html"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.exported_file: ExportedFile | None = None
        self.form: BaseExportForm | None = None

    def get_template_names(self) -> list[str]:
        """Form-specific template first, derived from the form's module: ``pkg.app.forms.FooBarForm`` ->
        ``pkg/app/foo_bar.html``; then the generic ``flat_file_exporter/form.html``."""
        form_class = self.get_form_class()
        directory = "/".join(form_class.__module__.split(".")[:-1])
        specific = f"{directory}/{to_snake_case(form_class.__name__.removesuffix('Form'))}.html"
        return [specific, "flat_file_exporter/form.html"]

    def get_form_class(self) -> type[BaseExportForm]:
        if not hasattr(self, "form_class"):
            raise NotImplementedError("Subclasses must define the form_class attribute")
        return self.form_class

    def get_kind(self) -> str:
        return getattr(
            self, "kind", to_snake_case(self.get_form_class().__name__.removesuffix("Form")).replace("_", "-")
        )

    def get_content_type(self) -> str:
        return getattr(self, "content_type_export", "application/octet-stream")

    def get_notes(self) -> str:
        return getattr(self, "notes", f"Requested by {self.request.user.get_username()}")

    def get_file_name(self) -> str:
        timestamp = now().strftime("%Y-%m-%d-%H-%M-%S")
        return f"{self.get_kind()}-{self.request.user.get_username()}-{timestamp}.{self.form.fileextension}"

    def get_task(self) -> Any:
        if hasattr(self, "task_ref"):
            return self.task_ref
        raise NotImplementedError("Subclasses must define the task_ref attribute")

    def get_valid_form(self, request: HttpRequest) -> BaseExportForm:
        form_class = self.get_form_class()
        self.form = form_class(request.POST, request.FILES) if request.method == "POST" else form_class()
        return self.form

    def get_context_data(self, request: HttpRequest | None = None, **kwargs: Any) -> dict[str, Any]:
        request = request or self.request
        context = super().get_context_data(**kwargs)
        context.update({"form": self.form or self.get_valid_form(request), "base_template": get_base_template()})
        return context

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        self.get_valid_form(request)
        return self.render_to_response(self.get_context_data(request))

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        self.get_valid_form(request)
        if not self.form.is_valid():
            return self.render_to_response(self.get_context_data(request))

        self.exported_file = ExportedFile.objects.create_export(
            kind=self.get_kind(),
            name=self.get_file_name(),
            notes=self.get_notes(),
            content_type=self.get_content_type(),
            requester_id=request.user.id,
            filetype=self.form.cleaned_data.get("filetype"),
        )
        try:
            result = self.get_task().delay(self.exported_file.id, **self.form.cleaned_data)
        except Exception as error:
            self.exported_file.lifecycle.failed(error)
            raise
        task_id = getattr(result, "id", None)
        if isinstance(task_id, str) and task_id:
            self.exported_file.task_id = task_id
            self.exported_file.save(update_fields=["task_id"])

        messages.success(
            request,
            _("Your request was received and is being processed. You can follow its status in the exports list."),
        )
        return redirect("flat_file_exporter:index")
