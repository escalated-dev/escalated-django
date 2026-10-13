from django.db import models
from django.db.models.lookups import Exact


class AccountIdentityField(models.CharField):
    """Morph identities compare case-sensitively on every supported database."""

    def db_parameters(self, connection):
        parameters = super().db_parameters(connection)
        parameters["collation"] = {"mysql": "utf8mb4_bin", "postgresql": "C", "sqlite": "BINARY"}.get(connection.vendor)
        return parameters


@AccountIdentityField.register_lookup
class AccountIdentityExact(Exact):
    """MySQL's utf8mb4_bin still ignores trailing spaces without binary casts."""

    def as_mysql(self, compiler, connection):
        # Keep the indexed equality predicate as a prefilter.
        sql, params = super().as_sql(compiler, connection)
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        return (
            f"({sql} AND CAST({lhs} AS BINARY) = CAST({rhs} AS BINARY))",
            [*params, *lhs_params, *rhs_params],
        )
