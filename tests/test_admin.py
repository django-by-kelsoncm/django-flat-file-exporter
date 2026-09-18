import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_admin_changelist_and_change_pages(client, export):
    admin = get_user_model().objects.create_superuser("root", password="pw")  # noqa: S106
    client.force_login(admin)
    assert client.get(reverse("admin:flat_file_exporter_exportedfile_changelist")).status_code == 200
    response = client.get(reverse("admin:flat_file_exporter_exportedfile_change", args=[export.pk]))
    assert response.status_code == 200 and export.validation_code in response.content.decode()
