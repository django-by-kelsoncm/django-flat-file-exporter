import pytest
from django.urls import reverse
from django.utils import translation

from flat_file_exporter.models import ExportedFile

pytestmark = pytest.mark.django_db


def test_english_is_the_default(client_logged, export):
    content = client_logged.get(reverse("flat_file_exporter:index")).content.decode()
    assert "Exports inbox" in content and "Requested at" in content


def test_index_is_translated_to_portuguese(client_logged, export):
    with translation.override("pt-br"):
        content = client_logged.get(reverse("flat_file_exporter:index")).content.decode()
    for text in ("Caixa de arquivos", "Data de solicitação", "Procurar...", "Situações", "Ver mais", "Solicitar"):
        assert text in content
    assert "Mostrando 1 até 1 de 1 registros" in content
    assert "Nenhum filtro ativo" in content


def test_javascript_strings_are_delivered_translated(client_logged, export):
    with translation.override("pt-br"):
        content = client_logged.get(reverse("flat_file_exporter:index")).content.decode()
    assert "window.flatFileExporterI18n" in content
    assert 'confirmTrash: "Tem certeza que deseja mover o arquivo %s para a lixeira?"' in content
    assert 'trashed: "Arquivo movido para a lixeira com sucesso"' in content


def test_form_page_is_translated(client_logged):
    with translation.override("pt-br"):
        content = client_logged.get(reverse("people_export")).content.decode()
    assert "Informação:" in content and "Exportar" in content and "Cancelar" in content


def test_labels_and_stored_messages_are_translated(export):
    with translation.override("pt-br"):
        assert ExportedFile.Status.GENERATED.label == "Arquivo gerado"
        assert ExportedFile.Status.GENERATED.short_display == "Gerado"
        assert ExportedFile._meta.verbose_name == "arquivo"
        export.lifecycle.failed()
    assert export.failure_cause == "Falha durante a geração do arquivo"
    assert export.failure_stack == "Sem stack trace disponível"


def test_default_notes_are_translated(client_logged):
    with translation.override("pt-br"):
        client_logged.post(reverse("people_export"), {"filetype": "csv"})
    assert ExportedFile.objects.get().notes == "Solicitado por ada"
