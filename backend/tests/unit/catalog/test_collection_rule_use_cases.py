"""Unit tests for the rule-based collection use cases (fakes, no DB)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import (
    AttributeRepository,
    CollectionRepository,
    CollectionRuleRepository,
    ProductRepository,
)
from src.application.catalog.use_cases import (
    GetCollectionRule,
    GetCollectionRuleMembers,
    RuleConditionInput,
    SetCollectionRule,
    SetCollectionRuleCommand,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Attribute, Collection, Product
from src.domain.catalog.enums import RuleOperator
from src.domain.catalog.exceptions import (
    CollectionNotFoundError,
    DuplicateRuleConditionError,
    InvalidAttributeCodeError,
    InvalidRuleOperatorError,
    UnknownAttributeError,
)
from src.domain.catalog.value_objects import (
    AttributeCode,
    AttributeValue,
    CollectionSlug,
    ProductCode,
    ProductTypeCode,
    RuleCondition,
)


class FakeCollectionRepository(CollectionRepository):
    def __init__(self) -> None:
        self._by_slug: dict[str, Collection] = {}

    def seed(self, collection: Collection) -> None:
        collection.id = len(self._by_slug) + 1
        self._by_slug[collection.slug.value] = collection

    def add(self, collection: Collection) -> Collection:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_slug(self, slug: str) -> Collection:
        try:
            return self._by_slug[slug]
        except KeyError:
            raise CollectionNotFoundError(slug) from None

    def exists_by_slug(self, slug: str) -> bool:  # pragma: no cover - unused here
        return slug in self._by_slug

    def list_all(self) -> list[Collection]:  # pragma: no cover - unused here
        return list(self._by_slug.values())


class FakeAttributeRepository(AttributeRepository):
    def __init__(self) -> None:
        self._codes: set[str] = set()

    def seed(self, *codes: str) -> None:
        self._codes.update(codes)

    def add(self, attribute: Attribute) -> Attribute:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> Attribute:  # pragma: no cover - unused here
        raise NotImplementedError

    def exists_by_code(self, code: str) -> bool:
        return code in self._codes

    def list_all(self) -> list[Attribute]:  # pragma: no cover - unused here
        raise NotImplementedError


class FakeProductRepository(ProductRepository):
    def __init__(self) -> None:
        self._products: list[Product] = []

    def seed(self, *products: Product) -> None:
        self._products.extend(products)

    def add(self, product: Product) -> Product:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> Product:  # pragma: no cover - unused here
        raise NotImplementedError

    def exists_by_code(self, code: str) -> bool:  # pragma: no cover - unused here
        return any(p.code.value == code for p in self._products)

    def list_all(self) -> list[Product]:
        return list(self._products)


class FakeCollectionRuleRepository(CollectionRuleRepository):
    def __init__(self) -> None:
        self._by_collection: dict[str, tuple[RuleCondition, ...]] = {}

    def replace(
        self, collection_slug: str, conditions: Sequence[RuleCondition]
    ) -> tuple[RuleCondition, ...]:
        stored = tuple(conditions)
        self._by_collection[collection_slug] = stored
        return stored

    def list_for_collection(self, collection_slug: str) -> tuple[RuleCondition, ...]:
        return self._by_collection.get(collection_slug, ())


class RecordingAudit(AuditRecorder):
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None,
        changes: tuple[FieldChange, ...],
    ) -> None:
        self.records.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "actor": actor,
                "changes": changes,
            }
        )


def _collection(slug: str = "dark-roasts") -> Collection:
    return Collection(slug=CollectionSlug(slug), name=slug.title())


def _product(code: str, **values: str) -> Product:
    return Product(
        code=ProductCode(code),
        name=code.title(),
        product_type=ProductTypeCode("coffee"),
        values=tuple(
            AttributeValue(attribute=AttributeCode(attr), value=value)
            for attr, value in values.items()
        ),
    )


def _input(attribute: str, operator: str, value: str) -> RuleConditionInput:
    return RuleConditionInput(attribute=attribute, operator=operator, value=value)


@pytest.fixture
def collections() -> FakeCollectionRepository:
    repo = FakeCollectionRepository()
    repo.seed(_collection())
    return repo


@pytest.fixture
def attributes() -> FakeAttributeRepository:
    repo = FakeAttributeRepository()
    repo.seed("roast-level", "decaf")
    return repo


@pytest.fixture
def products() -> FakeProductRepository:
    repo = FakeProductRepository()
    repo.seed(
        _product("house-blend", **{"roast-level": "dark"}),
        _product("breakfast", **{"roast-level": "light"}),
    )
    return repo


@pytest.fixture
def rule() -> FakeCollectionRuleRepository:
    return FakeCollectionRuleRepository()


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


def _set_use_case(
    rule: FakeCollectionRuleRepository,
    collections: FakeCollectionRepository,
    attributes: FakeAttributeRepository,
    audit: RecordingAudit,
) -> SetCollectionRule:
    return SetCollectionRule(rule, collections, attributes, audit)


class TestSetCollectionRule:
    def test_sets_a_rule_on_a_collection(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)

        result = use_case.execute(
            SetCollectionRuleCommand(
                collection="dark-roasts",
                conditions=(_input("roast-level", "equals", "dark"),),
            )
        )

        assert [(c.attribute.value, c.operator, c.value) for c in result] == [
            ("roast-level", RuleOperator.EQUALS, "dark")
        ]

    def test_replacing_with_an_empty_rule_clears_it(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)
        use_case.execute(
            SetCollectionRuleCommand(
                collection="dark-roasts", conditions=(_input("roast-level", "equals", "dark"),)
            )
        )

        result = use_case.execute(
            SetCollectionRuleCommand(collection="dark-roasts", conditions=())
        )

        assert result == ()

    def test_records_an_audit_event_with_before_and_after(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)

        use_case.execute(
            SetCollectionRuleCommand(
                collection="dark-roasts",
                conditions=(_input("roast-level", "equals", "dark"),),
            ),
            actor="42",
        )

        record = audit.records[-1]
        assert record["action"] == "collection.rule_changed"
        assert record["resource_type"] == "collection"
        assert record["actor"] == "42"
        change = record["changes"][0]
        assert change.before == ""
        assert change.after == "roast-level:equals:dark"

    def test_logs_a_structured_event(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)

        with capture_logs() as logs:
            use_case.execute(
                SetCollectionRuleCommand(
                    collection="dark-roasts",
                    conditions=(_input("roast-level", "equals", "dark"),),
                ),
                actor="42",
            )

        events = [e for e in logs if e["event"] == "collection_rule_set"]
        assert events and events[0]["actor"] == "42" and events[0]["count"] == 1

    def test_unknown_collection_raises_not_found(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)

        with pytest.raises(CollectionNotFoundError):
            use_case.execute(
                SetCollectionRuleCommand(
                    collection="ghost", conditions=(_input("roast-level", "equals", "dark"),)
                )
            )

    def test_unknown_attribute_raises_unknown_attribute(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)

        with pytest.raises(UnknownAttributeError):
            use_case.execute(
                SetCollectionRuleCommand(
                    collection="dark-roasts", conditions=(_input("ghost", "equals", "x"),)
                )
            )

    def test_does_not_persist_or_audit_when_an_attribute_is_unknown(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)

        with pytest.raises(UnknownAttributeError):
            use_case.execute(
                SetCollectionRuleCommand(
                    collection="dark-roasts", conditions=(_input("ghost", "equals", "x"),)
                )
            )

        assert rule.list_for_collection("dark-roasts") == ()
        assert audit.records == []

    def test_rejects_a_duplicate_condition(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)

        with pytest.raises(DuplicateRuleConditionError):
            use_case.execute(
                SetCollectionRuleCommand(
                    collection="dark-roasts",
                    conditions=(
                        _input("roast-level", "equals", "dark"),
                        _input("roast-level", "equals", "dark"),
                    ),
                )
            )

    def test_rejects_an_unknown_operator(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)

        with pytest.raises(InvalidRuleOperatorError):
            use_case.execute(
                SetCollectionRuleCommand(
                    collection="dark-roasts",
                    conditions=(_input("roast-level", "contains", "dark"),),
                )
            )

    def test_rejects_a_malformed_attribute_code(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(rule, collections, attributes, audit)

        with pytest.raises(InvalidAttributeCodeError):
            use_case.execute(
                SetCollectionRuleCommand(
                    collection="dark-roasts",
                    conditions=(_input("Not A Code", "equals", "dark"),),
                )
            )


class TestGetCollectionRule:
    def test_returns_the_rule(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        audit: RecordingAudit,
    ) -> None:
        _set_use_case(rule, collections, attributes, audit).execute(
            SetCollectionRuleCommand(
                collection="dark-roasts", conditions=(_input("roast-level", "equals", "dark"),)
            )
        )

        result = GetCollectionRule(rule, collections).execute(collection_slug="dark-roasts")

        assert [c.value for c in result] == ["dark"]

    def test_unknown_collection_raises_not_found(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
    ) -> None:
        with pytest.raises(CollectionNotFoundError):
            GetCollectionRule(rule, collections).execute(collection_slug="ghost")


class TestGetCollectionRuleMembers:
    def test_resolves_matching_products(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        _set_use_case(rule, collections, attributes, audit).execute(
            SetCollectionRuleCommand(
                collection="dark-roasts", conditions=(_input("roast-level", "equals", "dark"),)
            )
        )

        result = GetCollectionRuleMembers(rule, collections, products).execute(
            collection_slug="dark-roasts"
        )

        assert [p.value for p in result] == ["house-blend"]

    def test_a_collection_without_a_rule_resolves_to_nothing(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
    ) -> None:
        result = GetCollectionRuleMembers(rule, collections, products).execute(
            collection_slug="dark-roasts"
        )

        assert result == ()

    def test_logs_a_structured_event(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        attributes: FakeAttributeRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        _set_use_case(rule, collections, attributes, audit).execute(
            SetCollectionRuleCommand(
                collection="dark-roasts", conditions=(_input("roast-level", "equals", "dark"),)
            )
        )

        with capture_logs() as logs:
            GetCollectionRuleMembers(rule, collections, products).execute(
                collection_slug="dark-roasts"
            )

        events = [e for e in logs if e["event"] == "collection_rule_members_resolved"]
        assert events and events[0]["count"] == 1

    def test_unknown_collection_raises_not_found(
        self,
        rule: FakeCollectionRuleRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
    ) -> None:
        with pytest.raises(CollectionNotFoundError):
            GetCollectionRuleMembers(rule, collections, products).execute(collection_slug="ghost")
