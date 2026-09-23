import pytest
from django import forms
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import override_settings

from flat_file_exporter import forms as forms_module
from flat_file_exporter.forms import (
    BaseExportForm,
    ExportColumn,
    ExportFilter,
    ExportMetadata,
    to_snake_case,
)
from flat_file_exporter.templatetags import flat_file_exporter_tags as tags
from tests.sampleapp.forms import PeopleExportForm, RestrictedExportForm


def test_to_snake_case():
    assert to_snake_case("PeopleExport") == "people_export"


def test_metadata_from_docstring_and_fields():
    metadata = PeopleExportForm().meta_data
    assert metadata.title == "People list"
    assert metadata.description == "All the people, with optional filtering."
    assert metadata.link == "/people/"
    assert [crumb["title"] for crumb in metadata.breadcrumbs] == ["Exports", "People list"]
    filter_titles = [f.title for f in metadata.filters]
    assert filter_titles == ["Minimum age"]  # the hidden filetype field is not a filter
    minimum = next(f for f in metadata.filters if f.title == "Minimum age")
    assert minimum.required is False and minimum.description == "Only people at least this old"
    assert [c.name for c in metadata.columns] == ["name", "age"]


def test_metadata_as_dict_roundtrip():
    data = PeopleExportForm().meta_data.as_dict()
    assert data["title"] == "People list"
    assert data["filters"][0]["title"]
    assert data["columns"][0] == {"name": "name", "description": "Full name"}
    empty = ExportMetadata("t", "l", [], "d").as_dict()
    assert empty["filters"] is None and empty["columns"] is None
    assert ExportFilter("f").as_dict() == {"title": "f", "description": None, "required": True}
    assert ExportColumn("c").as_dict() == {"name": "c", "description": None}


def test_description_html_and_title_property():
    form = PeopleExportForm()
    assert form.title == "People list"
    assert "<p>All the people" in form.description_html


def test_title_and_description_fallbacks_without_docstring():
    class Undocumented_Report(BaseExportForm):  # noqa: N801
        url_name = None

    form = Undocumented_Report()
    assert form.get_default_title() == "Undocumented Report"
    assert form.get_default_description() == "Undocumented Report"


def test_link_guess_without_url_name_returns_empty():
    class GuessedForm(BaseExportForm):
        pass

    GuessedForm.__module__ = "tests.sampleapp.forms"
    assert GuessedForm().get_default_link() == ""
    GuessedForm.__module__ = "not_an_installed_app.forms"
    assert GuessedForm().get_default_link() == ""
    assert [c["title"] for c in GuessedForm().get_default_breadcrumbs()] == ["Exports"]


@pytest.mark.django_db
def test_get_export_forms_discovers_and_caches():
    BaseExportForm._export_forms = None
    found = BaseExportForm.get_export_forms()
    assert PeopleExportForm in found and BaseExportForm not in found
    assert BaseExportForm.get_export_forms() is found


def test_get_export_forms_propagates_real_import_errors(monkeypatch):
    import importlib

    BaseExportForm._export_forms = None
    real = importlib.import_module

    def broken(name, *args, **kwargs):
        if name == "tests.sampleapp.forms":
            raise ModuleNotFoundError("No module named 'inner'", name="inner")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", broken)
    try:
        with pytest.raises(ModuleNotFoundError):
            BaseExportForm.get_export_forms()
    finally:
        BaseExportForm._export_forms = None


@pytest.mark.django_db
def test_get_required_permissions_reads_the_view_permission_required():
    assert PeopleExportForm.get_required_permissions() == ("flat_file_exporter.view_exportedfile",)
    assert RestrictedExportForm.get_required_permissions() == (
        "flat_file_exporter.view_exportedfile",
        "flat_file_exporter.delete_exportedfile",
    )


def test_get_required_permissions_empty_without_a_link():
    class NoLinkForm(BaseExportForm):
        pass

    NoLinkForm.__module__ = "not_an_installed_app.forms"
    assert NoLinkForm.get_required_permissions() == ()


def test_get_required_permissions_empty_when_the_view_has_none():
    class AdminIndexForm(BaseExportForm):
        url_name = "admin:index"

    assert AdminIndexForm.get_required_permissions() == ()


def test_get_required_permissions_empty_when_the_link_does_not_resolve(monkeypatch):
    from django.urls import Resolver404

    def boom(path):
        raise Resolver404

    monkeypatch.setattr(forms_module, "resolve", boom)
    assert PeopleExportForm.get_required_permissions() == ()


@pytest.mark.django_db
def test_is_visible_to_without_required_permissions_is_always_true():
    class NoLinkForm(BaseExportForm):
        pass

    NoLinkForm.__module__ = "not_an_installed_app.forms"
    assert NoLinkForm.is_visible_to(get_user_model().objects.create_user("anyone", password="pw"))  # noqa: S106


@pytest.mark.django_db
def test_is_visible_to_checks_every_required_permission():
    from django.contrib.auth.models import Permission

    partial = get_user_model().objects.create_user("partial", password="pw")  # noqa: S106
    partial.user_permissions.add(Permission.objects.get(codename="view_exportedfile"))
    assert PeopleExportForm.is_visible_to(partial) is True
    assert RestrictedExportForm.is_visible_to(partial) is False

    full = get_user_model().objects.create_user("full", password="pw")  # noqa: S106
    full.user_permissions.add(
        Permission.objects.get(codename="view_exportedfile"), Permission.objects.get(codename="delete_exportedfile")
    )
    assert RestrictedExportForm.is_visible_to(full) is True


def test_get_statuses():
    statuses = BaseExportForm.get_statuses()
    assert [s["value"] for s in statuses] == [0, 1, 5, 9, 10]


def test_filetypes_mapped_and_extension():
    form = PeopleExportForm()
    assert {ft["filetype"] for ft in form.filetypes_mapped} >= {"csv", "xlsx"}
    assert form.fileextension == "csv.zip"
    bound = PeopleExportForm({"filetype": "xlsx"})
    assert bound.is_valid() and bound.fileextension == "xlsx.zip"
    pdf = PeopleExportForm({"filetype": "pdf"})
    assert pdf.is_valid() and pdf.fileextension == "pdf"
    with override_settings(FLAT_FILE_EXPORTER_FILETYPES={"csv": None}):
        assert "csv" not in {ft["filetype"] for ft in PeopleExportForm().filetypes_mapped}


def test_fieldset_groups():
    class Grouped(BaseExportForm):
        fieldsets = [
            ("A", {"fields": []}),
            ("B", {"fields": [], "tabbed": True}),
            ("C", {"fields": [], "tabbed": True}),
            ("D", {}),
        ]

    groups = Grouped().fieldset_groups
    assert [g["type"] for g in groups] == ["block", "tabs", "block"]
    assert len(groups[1]["items"]) == 2
    assert PeopleExportForm().fieldset_groups == []


def test_tags_is_checkbox_and_add_class():
    class F(forms.Form):
        flag = forms.BooleanField(required=False)
        name = forms.CharField(widget=forms.TextInput(attrs={"class": "a"}))

    form = F()
    assert tags.is_checkbox(form["flag"]) and not tags.is_checkbox(form["name"])
    assert 'class="a b"' in tags.add_class(form["name"], "b")
    assert 'class="b"' in tags.add_class(form["flag"], "b")


def test_tags_bootstrap_col_class():
    assert tags.bootstrap_col_class(["a", "b"]) == "col-md-6"
    assert tags.bootstrap_col_class([]) == "col-md-12"
    assert tags.bootstrap_col_class(5) == "col-md-12"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0s"), (-3, "0s"), (38, "38s"), (2336, "38m56s"), (3902, "1h5m2s"), ("x", ""), (None, "")],
)
def test_tags_format_duration(seconds, expected):
    assert tags.format_duration(seconds) == expected


def test_tags_render_markdown_in_template():
    html = Template("{% load flat_file_exporter_tags %}{{ text|render_markdown }}").render(Context({"text": "**hi**"}))
    assert "<strong>hi</strong>" in html
    assert tags.render_markdown(None) == ""
