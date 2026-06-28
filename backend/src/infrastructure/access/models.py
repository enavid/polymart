"""The access app owns no ORM models of its own.

This module exists deliberately: Django only emits ``post_migrate`` for apps
that have a models module, and the access app relies on that signal to sync the
domain permission registry onto Django Groups (see ``apps.AccessConfig``).
"""

from __future__ import annotations
