"""Composition root for the inventory admin slice.

Wires the Django repositories (and the audit recorder) into the inventory use cases.
Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.inventory.use_cases import (
    AdjustStockOnHand,
    CreateStockSource,
    GetSourceStock,
    GetStockPolicy,
    GetStockSource,
    ListStockSources,
    SetStockOnHand,
    SetStockPolicy,
)
from src.infrastructure.inventory.repositories import (
    DjangoStockLevelRepository,
    DjangoStockPolicyRepository,
    DjangoStockSourceRepository,
)
from src.interface.api.audit.container import build_audit_recorder


def build_list_stock_sources() -> ListStockSources:
    return ListStockSources(DjangoStockSourceRepository())


def build_create_stock_source() -> CreateStockSource:
    return CreateStockSource(DjangoStockSourceRepository(), build_audit_recorder())


def build_get_stock_source() -> GetStockSource:
    return GetStockSource(DjangoStockSourceRepository())


def build_get_source_stock() -> GetSourceStock:
    return GetSourceStock(DjangoStockLevelRepository())


def build_set_stock_on_hand() -> SetStockOnHand:
    return SetStockOnHand(DjangoStockLevelRepository(), build_audit_recorder())


def build_adjust_stock_on_hand() -> AdjustStockOnHand:
    return AdjustStockOnHand(DjangoStockLevelRepository(), build_audit_recorder())


def build_get_stock_policy() -> GetStockPolicy:
    return GetStockPolicy(DjangoStockPolicyRepository())


def build_set_stock_policy() -> SetStockPolicy:
    return SetStockPolicy(DjangoStockPolicyRepository(), build_audit_recorder())
