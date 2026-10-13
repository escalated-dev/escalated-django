from django.db import models


class AccountIdentityField(models.CharField):
    """Morph identities compare case-sensitively on every supported database."""

    def db_parameters(self, connection):
        parameters = super().db_parameters(connection)
        parameters["collation"] = {"mysql": "utf8mb4_bin", "postgresql": "C", "sqlite": "BINARY"}.get(connection.vendor)
        return parameters
