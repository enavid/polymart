"""Django ORM model for address persistence.

Infrastructure detail, intentionally separate from the domain aggregate. The
repository maps between the two so the domain never depends on the ORM.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models

_ADDRESS_ID_MAX_LENGTH = 40
_RECIPIENT_NAME_MAX_LENGTH = 200
_PHONE_NUMBER_MAX_LENGTH = 20
_PROVINCE_MAX_LENGTH = 100
_CITY_MAX_LENGTH = 100
_POSTAL_CODE_MAX_LENGTH = 10
_ADDRESS_LINE_MAX_LENGTH = 255


class AddressModel(models.Model):
    """One saved shipping address (one row per address).

    The owner is a hard FK to the user (an address is meaningless without its owner).
    ``address_id`` is the public, unguessable, unique reference used in URLs -- never
    the database ``id``. A partial unique constraint enforces "at most one default per
    owner" as a hard database invariant, backstopping the application-layer swap.
    """

    address_id = models.CharField(max_length=_ADDRESS_ID_MAX_LENGTH, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="addresses", on_delete=models.CASCADE
    )
    recipient_name = models.CharField(max_length=_RECIPIENT_NAME_MAX_LENGTH)
    phone_number = models.CharField(max_length=_PHONE_NUMBER_MAX_LENGTH)
    province = models.CharField(max_length=_PROVINCE_MAX_LENGTH)
    city = models.CharField(max_length=_CITY_MAX_LENGTH)
    postal_code = models.CharField(max_length=_POSTAL_CODE_MAX_LENGTH)
    line1 = models.CharField(max_length=_ADDRESS_LINE_MAX_LENGTH)
    line2 = models.CharField(max_length=_ADDRESS_LINE_MAX_LENGTH, blank=True, default="")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField()

    class Meta:
        app_label = "address"
        db_table = "address_address"
        # Default first, then newest first: the natural read order for an address book.
        ordering = ("-is_default", "-id")
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["owner", "-id"], name="idx_address_owner_recent"),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(is_default=True),
                name="uniq_default_address_per_owner",
            ),
        ]
        verbose_name = "address"
        verbose_name_plural = "addresses"

    def __str__(self) -> str:
        return self.address_id
