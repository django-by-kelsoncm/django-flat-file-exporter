import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from flat_file_exporter.models import ExportedFile, ExportStakeholder


@pytest.fixture(autouse=True)
def fresh_storage(settings):
    """Each test gets its own in-memory storage (reassigning STORAGES resets Django's storage handler)."""
    settings.STORAGES = {**settings.STORAGES, "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}


@pytest.fixture
def user(db):
    account = get_user_model().objects.create_user("ada", password="pw")  # noqa: S106
    account.user_permissions.add(Permission.objects.get(codename="view_exportedfile"))
    return account


@pytest.fixture
def other_user(db):
    account = get_user_model().objects.create_user("alan", password="pw")  # noqa: S106
    account.user_permissions.add(Permission.objects.get(codename="view_exportedfile"))
    return account


@pytest.fixture
def client_logged(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def export(user):
    return ExportedFile.objects.create_export(
        kind="people", name="people.csv.zip", notes="n", content_type="application/zip", requester_id=user.id
    )


@pytest.fixture
def generated(export):
    from django.core.files.base import ContentFile

    from flat_file_exporter.conf import get_storage

    export.storage_key = get_storage().save("flat_file_exporter/people.csv.zip", ContentFile(b"zipdata"))
    export.status = ExportedFile.Status.GENERATED
    export.save()
    return export


@pytest.fixture
def stakeholder_of(db):
    def make(exported_file, user):
        return ExportStakeholder.objects.create(
            user=user, exported_file=exported_file, role=ExportStakeholder.Role.RECIPIENT
        )

    return make
