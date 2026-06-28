"""Django ORM model for audit-log persistence.

An infrastructure detail, intentionally separate from the domain ``AuditEntry``.
The trail maps between the two so the domain never depends on the ORM. The table
is append-only: rows are inserted, never updated or deleted.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

# Generous fixed widths: actions/resource types are short identifiers, and the
# actor/resource ids are stringified primary keys.
_ACTION_MAX_LENGTH = 100
_RESOURCE_TYPE_MAX_LENGTH = 64
_RESOURCE_ID_MAX_LENGTH = 64
_ACTOR_MAX_LENGTH = 64


class AuditLogModel(models.Model):
    """Storage representation of a single audited change."""

    action = models.CharField(max_length=_ACTION_MAX_LENGTH)
    resource_type = models.CharField(max_length=_RESOURCE_TYPE_MAX_LENGTH)
    resource_id = models.CharField(max_length=_RESOURCE_ID_MAX_LENGTH)
    # The actor's stable user id (never the phone number / PII). NULL means a
    # system-initiated change with no human actor; the domain forbids a blank
    # actor, so an empty string could never legitimately carry that meaning.
    actor = models.CharField(max_length=_ACTOR_MAX_LENGTH, null=True, blank=True)  # noqa: DJ001 - NULL is a meaningful "no actor", distinct from the domain-forbidden empty string
    # {field: {"before": <scalar|null>, "after": <scalar|null>}} per changed field.
    changes = models.JSONField(default=dict)
    # Stamped from the application clock, consistent with the domain's "now".
    occurred_at = models.DateTimeField()

    class Meta:
        app_label = "audit"
        db_table = "audit_log"
        ordering = ("-occurred_at",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["resource_type", "resource_id", "-occurred_at"]),
            models.Index(fields=["action", "-occurred_at"]),
        ]

    def __str__(self) -> str:
        return f"audit:{self.action}:{self.pk}"
