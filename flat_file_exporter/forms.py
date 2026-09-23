import importlib
import re
from typing import Any, TypedDict

import markdown
from django import forms
from django.apps import apps
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from flat_file_exporter.conf import get_filetypes
from flat_file_exporter.models import ExportedFile


def to_snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


class StatusItem(TypedDict):
    value: int
    display: str
    short_display: str
    icon: str


class ExportFilter:
    """Metadata about a filter of an export form (shown in the catalog)."""

    def __init__(self, title: str, description: str | None = None, required: bool = True):
        self.title = title
        self.description = description
        self.required = required

    def as_dict(self) -> dict[str, Any]:
        return {"title": self.title, "description": self.description, "required": self.required}


class ExportColumn:
    """Metadata about a column of the generated file (shown in the catalog)."""

    def __init__(self, name: str, description: str | None = None):
        self.name = name
        self.description = description

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}


class ExportMetadata:
    """Everything the catalog page shows about an export form."""

    def __init__(
        self,
        title: str,
        link: str,
        breadcrumbs: list[dict[str, str]],
        description: str,
        filters: list[ExportFilter] | None = None,
        columns: list[ExportColumn] | None = None,
    ):
        self.title = title
        self.link = link
        self.breadcrumbs = breadcrumbs
        self.description = description
        self.filters = filters
        self.columns = columns

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "link": self.link,
            "breadcrumbs": self.breadcrumbs,
            "description": self.description,
            "filters": [item.as_dict() for item in self.filters] if self.filters else None,
            "columns": [item.as_dict() for item in self.columns] if self.columns else None,
        }


class BaseExportForm(forms.Form):
    """Base class for the form of an export; subclasses are discovered in each installed app's ``forms`` module.

    The first non-blank docstring line is the title and the following lines (until a line starting with ``@``) are the
    description, in Markdown. Set ``url_name`` to the (namespaced) URL name of the view that serves the form, and
    optionally ``columns`` (a list of :class:`ExportColumn`) to describe the generated file.
    """

    url_name: str | None = None
    _export_forms: list[type["BaseExportForm"]] | None = None

    filetype = forms.CharField(widget=forms.HiddenInput(), initial="csv", required=True, label=_("File type"))

    @property
    def meta_data(self) -> ExportMetadata:
        return self.get_metadata()

    @property
    def fieldset_groups(self) -> list[dict[str, Any]]:
        """Consecutive fieldsets grouped by their ``tabbed`` option, for template rendering."""
        if not getattr(self, "fieldsets", None):
            return []
        groups: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for fieldset in self.fieldsets:
            options = fieldset[1] if len(fieldset) > 1 else {}
            group_type = "tabs" if options.get("tabbed", False) else "block"
            if current is None or current["type"] != group_type:
                if current is not None:
                    groups.append(current)
                current = {"type": group_type, "items": [fieldset]}
            else:
                current["items"].append(fieldset)
        if current is not None:
            groups.append(current)
        return groups

    @property
    def title(self) -> str:
        return self.meta_data.title

    @property
    def description(self) -> str:
        return self.meta_data.description

    @property
    def description_html(self) -> str:
        return markdown.markdown(self.description or "")

    @property
    def filetypes(self) -> list[str]:
        """Filetypes offered by this form (default: every configured one). Subclasses may restrict."""
        return list(get_filetypes())

    @property
    def filetypes_mapped(self) -> list[dict[str, str]]:
        available = get_filetypes()
        return [{**available[filetype], "filetype": filetype} for filetype in self.filetypes if filetype in available]

    @property
    def fileextension(self) -> str:
        """Extension of the generated file: renderers zip their output, except pdf and docx."""
        cleaned = getattr(self, "cleaned_data", None)
        if cleaned and cleaned.get("filetype"):
            filetype = cleaned["filetype"]
        else:
            filetype = self.fields["filetype"].initial or "txt"
        if filetype in ("pdf", "docx"):
            return filetype
        return f"{filetype}.zip"

    def get_metadata(self) -> ExportMetadata:
        if not hasattr(self, "_metadata"):
            self._metadata = ExportMetadata(
                title=self.get_default_title(),
                link=self.get_default_link(),
                breadcrumbs=self.get_default_breadcrumbs(),
                description=self.get_default_description(),
                filters=self.get_default_filters(),
                columns=self.get_columns(),
            )
        return self._metadata

    def get_default_link(self) -> str:
        """URL of the view for this form: ``url_name``, or ``<namespace>:<form_name_in_snake_case>`` as a guess,
        trying the app's ``label`` (the common case) and its full dotted ``name`` (for projects that namespace
        ``include()`` with ``app_name = SomeConfig.name`` instead of the auto-derived short label)."""
        if self.url_name:
            return reverse(self.url_name)
        app_config = apps.get_containing_app_config(type(self).__module__)
        if app_config is None:
            return ""
        guess = to_snake_case(type(self).__name__.removesuffix("Form"))
        for namespace in dict.fromkeys((app_config.label, app_config.name)):
            try:
                return reverse(f"{namespace}:{guess}")
            except NoReverseMatch:
                continue
        return ""

    def get_default_title(self) -> str:
        for line in (type(self).__doc__ or "").split("\n"):
            if line.strip():
                return line.strip()
        return re.sub(r"\s+", " ", re.sub(r"([A-Z])", r" \1", type(self).__name__.replace("_", " "))).strip()

    def get_default_description(self) -> str:
        lines = (type(self).__doc__ or "").split("\n")
        start = next((index for index, line in enumerate(lines) if line.strip()), None)
        if start is None:
            return self.get_default_title()
        description: list[str] = []
        for line in lines[start + 1 :]:
            if line.strip().startswith("@"):
                break
            description.append(line)
        return "\n".join(description).strip()

    def get_default_breadcrumbs(self) -> list[dict[str, str]]:
        crumbs = [{"title": gettext("Exports"), "link": reverse("flat_file_exporter:index")}]
        link = self.get_default_link()
        if link:
            crumbs.append({"title": self.get_default_title(), "link": link})
        return crumbs

    def get_default_filters(self) -> list[ExportFilter]:
        return [
            ExportFilter(
                title=field.label or name.capitalize(),
                description=field.help_text or None,
                required=field.required,
            )
            for name, field in self.fields.items()
            if not field.widget.is_hidden
        ]

    def get_columns(self) -> list[ExportColumn]:
        return [
            ExportColumn(name=column.name, description=column.description) for column in getattr(self, "columns", [])
        ]

    @classmethod
    def get_required_permissions(cls) -> tuple[str, ...]:
        """Permissions required to request this export, read off the ``permission_required`` of the view that serves
        it (resolved from ``get_default_link()``). Empty when the link or the view's permissions can't be
        determined -- the form is then treated as visible to everyone, same as before this check existed."""
        link = cls().get_default_link()
        if not link:
            return ()
        try:
            view_class = getattr(resolve(link).func, "view_class", None)
        except Resolver404:
            return ()
        permission_required = getattr(view_class, "permission_required", None)
        if not permission_required:
            return ()
        return (permission_required,) if isinstance(permission_required, str) else tuple(permission_required)

    @classmethod
    def is_visible_to(cls, user) -> bool:
        """Whether ``user`` has every permission required by the view that serves this form."""
        permissions = cls.get_required_permissions()
        return not permissions or user.has_perms(permissions)

    @classmethod
    def get_export_forms(cls) -> list[type["BaseExportForm"]]:
        """Every concrete ``BaseExportForm`` subclass found in the ``forms`` modules of the installed apps (cached)."""
        if BaseExportForm._export_forms is None:
            found: list[type[BaseExportForm]] = []
            for app_config in apps.get_app_configs():
                module_name = f"{app_config.name}.forms"
                try:
                    forms_module = importlib.import_module(module_name)
                except ModuleNotFoundError as error:
                    if error.name == module_name:
                        continue
                    raise
                for attribute in vars(forms_module).values():
                    if (
                        isinstance(attribute, type)
                        and issubclass(attribute, BaseExportForm)
                        and attribute is not BaseExportForm
                        and attribute not in found
                    ):
                        found.append(attribute)
            BaseExportForm._export_forms = found
        return BaseExportForm._export_forms

    @classmethod
    def get_statuses(cls) -> list[StatusItem]:
        return [
            {"value": s.value, "display": str(s.label), "short_display": s.short_display, "icon": s.icon}
            for s in ExportedFile.Status
        ]
