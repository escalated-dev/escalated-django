"""
ImportJob.credentials is an EncryptedJSONField, which imports ``cryptography``
the moment a value is written or read. The package has to be a declared
dependency: on an install that has only what pyproject.toml lists, creating an
import job would otherwise raise ModuleNotFoundError and the import wizard's
first step would answer 500.

CI installs the package from pyproject.toml alone, so these tests fail there if
the dependency is ever dropped again.
"""

import pytest
from django.db import connection

from escalated.models import ImportJob

CREDENTIALS = {"subdomain": "acme", "api_token": "secret-token-123"}


@pytest.mark.django_db
class TestImportJobCredentials:
    def test_saves_and_reads_back_credentials(self):
        job = ImportJob.objects.create(platform="zendesk", credentials=CREDENTIALS)

        job.refresh_from_db()

        assert job.credentials == CREDENTIALS

    def test_credentials_are_encrypted_at_rest(self):
        ImportJob.objects.create(platform="zendesk", credentials=CREDENTIALS)

        table = connection.ops.quote_name(ImportJob._meta.db_table)
        column = connection.ops.quote_name("credentials")
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {column} FROM {table}")
            (stored,) = cursor.fetchone()

        assert stored.startswith("enc::")
        assert "secret-token-123" not in stored
