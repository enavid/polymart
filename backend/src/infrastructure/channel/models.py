"""Django ORM model for channel persistence.

This is an infrastructure detail, intentionally separate from the domain
``Channel`` entity. The repository maps between the two so the domain never
depends on the ORM.
"""
from __future__ import annotations

from django.db import models


class ChannelModel(models.Model):
    """Storage representation of a selling channel."""

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    currency_code = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "channel"
        db_table = "channel"
        ordering = ("slug",)
        verbose_name = "channel"
        verbose_name_plural = "channels"

    def __str__(self) -> str:
        return self.slug
