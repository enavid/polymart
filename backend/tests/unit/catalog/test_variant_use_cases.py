"""Unit tests for the variant use cases (fakes, no Django/DB)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import (
    AttributeRepository,
    ProductRepository,
    ProductTypeRepository,
    VariantRepository,
)
from src.application.catalog.use_cases import (
    AttributeValueInput,
    CreateVariant,
    CreateVariantCommand,
    GetVariant,
    ListProductVariants,
    MediaInput,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Attribute, Product, ProductType, ProductVariant
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeNotFoundError,
    InvalidAttributeValueError,
    MissingRequiredAttributeError,
    ProductNotFoundError,
    ProductTypeNotFoundError,
    UnassignedAttributeError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
)
from src.domain.catalog.value_objects import (
    AttributeChoice,
    AttributeCode,
    ProductCode,
    ProductTypeCode,
)


class FakeAttributeRepository(AttributeRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, Attribute] = {}
        self._sequence = 0

    def seed(self, attribute: Attribute) -> None:
        self._sequence += 1
        attribute.id = self._sequence
        self._by_code[attribute.code.value] = attribute

    def add(self, attribute: Attribute) -> Attribute:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> Attribute:
        try:
            return self._by_code[code]
        except KeyError:
            raise AttributeNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:  # pragma: no cover - unused here
        return code in self._by_code

    def list_all(self) -> list[Attribute]:  # pragma: no cover - unused here
        return [self._by_code[c] for c in sorted(self._by_code)]


class FakeProductTypeRepository(ProductTypeRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, ProductType] = {}
        self._sequence = 0

    def seed(self, product_type: ProductType) -> None:
        self._sequence += 1
        product_type.id = self._sequence
        self._by_code[product_type.code.value] = product_type

    def add(self, product_type: ProductType) -> ProductType:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> ProductType:
        try:
            return self._by_code[code]
        except KeyError:
            raise ProductTypeNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:  # pragma: no cover - unused here
        return code in self._by_code

    def list_all(self) -> list[ProductType]:  # pragma: no cover - unused here
        return [self._by_code[c] for c in sorted(self._by_code)]


class FakeProductRepository(ProductRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, Product] = {}

    def seed(self, product: Product) -> None:
        product.id = len(self._by_code) + 1
        self._by_code[product.code.value] = product

    def add(self, product: Product) -> Product:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> Product:
        try:
            return self._by_code[code]
        except KeyError:
            raise ProductNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:  # pragma: no cover - unused here
        return code in self._by_code

    def list_all(self) -> list[Product]:  # pragma: no cover - unused here
        return list(self._by_code.values())


class FakeVariantRepository(VariantRepository):
    def __init__(self) -> None:
        self._by_sku: dict[str, ProductVariant] = {}
        self._sequence = 0

    def add(self, variant: ProductVariant) -> ProductVariant:
        sku = variant.sku.value
        if sku in self._by_sku:
            raise VariantAlreadyExistsError(sku)
        self._sequence += 1
        variant.id = self._sequence
        self._by_sku[sku] = variant
        return variant

    def get_by_sku(self, sku: str) -> ProductVariant:
        try:
            return self._by_sku[sku]
        except KeyError:
            raise VariantNotFoundError(sku) from None

    def exists_by_sku(self, sku: str) -> bool:
        return sku in self._by_sku

    def list_for_product(self, product_code: str) -> list[ProductVariant]:
        return [
            self._by_sku[s]
            for s in sorted(self._by_sku)
            if self._by_sku[s].product.value == product_code
        ]


class RecordedAudit:
    def __init__(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None,
        changes: tuple[FieldChange, ...],
    ) -> None:
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.actor = actor
        self.changes = changes


class FakeAuditRecorder(AuditRecorder):
    def __init__(self) -> None:
        self.calls: list[RecordedAudit] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: Sequence[FieldChange] = (),
    ) -> None:
        self.calls.append(RecordedAudit(action, resource_type, resource_id, actor, tuple(changes)))


def _attribute(code: str, input_type: AttributeInputType, **kwargs: object) -> Attribute:
    return Attribute(
        code=AttributeCode(code),
        name=code.title(),
        input_type=input_type,
        required=bool(kwargs.get("required", False)),
        choices=tuple(kwargs.get("choices", ())),  # type: ignore[arg-type]
    )


@pytest.fixture
def attributes() -> FakeAttributeRepository:
    repo = FakeAttributeRepository()
    repo.seed(_attribute("weight", AttributeInputType.NUMBER))
    repo.seed(
        _attribute(
            "grind",
            AttributeInputType.DROPDOWN,
            choices=(
                AttributeChoice(value="whole-bean", label="Whole bean"),
                AttributeChoice(value="espresso", label="Espresso"),
            ),
        )
    )
    return repo


@pytest.fixture
def product_types() -> FakeProductTypeRepository:
    repo = FakeProductTypeRepository()
    repo.seed(
        ProductType(
            code=ProductTypeCode("coffee"),
            name="Coffee",
            variant_attributes=(AttributeCode("weight"), AttributeCode("grind")),
        )
    )
    return repo


@pytest.fixture
def products() -> FakeProductRepository:
    repo = FakeProductRepository()
    repo.seed(
        Product(
            code=ProductCode("house-blend"),
            name="House Blend",
            product_type=ProductTypeCode("coffee"),
        )
    )
    return repo


@pytest.fixture
def variants() -> FakeVariantRepository:
    return FakeVariantRepository()


@pytest.fixture
def audit() -> FakeAuditRecorder:
    return FakeAuditRecorder()


def _use_case(
    variants: FakeVariantRepository,
    products: FakeProductRepository,
    product_types: FakeProductTypeRepository,
    attributes: FakeAttributeRepository,
    audit: FakeAuditRecorder,
) -> CreateVariant:
    return CreateVariant(variants, products, product_types, attributes, audit)


def _command(**overrides: object) -> CreateVariantCommand:
    defaults: dict[str, object] = {
        "product": "house-blend",
        "sku": "coffee-250",
        "name": "250g Bag",
    }
    defaults.update(overrides)
    return CreateVariantCommand(**defaults)  # type: ignore[arg-type]


class TestCreateVariant:
    def test_persists_a_variant_with_a_canonical_sku(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        variant = _use_case(variants, products, product_types, attributes, audit).execute(
            _command()
        )

        assert variant.id is not None
        assert variant.product.value == "house-blend"
        # The SKU is canonicalized to uppercase regardless of how it was supplied.
        assert variant.sku.value == "COFFEE-250"

    def test_rejects_a_variant_for_an_unknown_product(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with pytest.raises(ProductNotFoundError):
            _use_case(variants, products, product_types, attributes, audit).execute(
                _command(product="ghost")
            )

        assert variants.list_for_product("ghost") == []

    def test_rejects_a_duplicate_sku(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        use_case = _use_case(variants, products, product_types, attributes, audit)
        use_case.execute(_command())

        with pytest.raises(VariantAlreadyExistsError):
            # Same SKU in a different case must still collide.
            use_case.execute(_command(sku="COFFEE-250", name="Another"))

    def test_writes_a_durable_audit_entry(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        variant = _use_case(variants, products, product_types, attributes, audit).execute(
            _command(values=(AttributeValueInput(attribute="weight", value="250"),)),
            actor="operator",
        )

        calls = [c for c in audit.calls if c.action == "variant.created"]
        assert len(calls) == 1
        call = calls[0]
        assert call.resource_type == "variant"
        assert call.resource_id == str(variant.id)
        assert call.actor == "operator"
        recorded = {change.field: change.after for change in call.changes}
        assert recorded["sku"] == "COFFEE-250"
        assert recorded["product"] == "house-blend"
        assert recorded["value_count"] == 1

    def test_logs_the_actor(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with capture_logs() as logs:
            _use_case(variants, products, product_types, attributes, audit).execute(
                _command(), actor="operator"
            )

        events = [e for e in logs if e["event"] == "variant_created"]
        assert events and events[0]["actor"] == "operator"

    def test_persists_media_and_audits_its_count(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        variant = _use_case(variants, products, product_types, attributes, audit).execute(
            _command(
                media=(
                    MediaInput(url="/media/front.jpg", alt_text="Front"),
                    MediaInput(url="/media/back.jpg"),
                )
            )
        )

        assert [m.url for m in variant.media] == ["/media/front.jpg", "/media/back.jpg"]
        call = next(c for c in audit.calls if c.action == "variant.created")
        recorded = {change.field: change.after for change in call.changes}
        assert recorded["media_count"] == 2


class TestOptionConformance:
    """Variant values are checked against the product type's variant attributes,
    reusing the same conformance service the product head uses."""

    def test_normalizes_conforming_option_values(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        variant = _use_case(variants, products, product_types, attributes, audit).execute(
            _command(
                values=(
                    AttributeValueInput(attribute="grind", value=" espresso "),
                    AttributeValueInput(attribute="weight", value="250"),
                )
            )
        )

        # Values come back canonicalized and in the type's declared order.
        assert [(v.attribute.value, v.value) for v in variant.values] == [
            ("weight", "250"),
            ("grind", "espresso"),
        ]

    def test_rejects_a_value_for_a_product_level_attribute(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        # "origin" is not a variant attribute of the coffee type.
        attributes.seed(_attribute("origin", AttributeInputType.PLAIN_TEXT))

        with pytest.raises(UnassignedAttributeError):
            _use_case(variants, products, product_types, attributes, audit).execute(
                _command(values=(AttributeValueInput(attribute="origin", value="ethiopia"),))
            )

        assert variants.exists_by_sku("COFFEE-250") is False

    def test_rejects_a_malformed_option_value(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with pytest.raises(InvalidAttributeValueError):
            _use_case(variants, products, product_types, attributes, audit).execute(
                _command(values=(AttributeValueInput(attribute="weight", value="heavy"),))
            )

    def test_rejects_a_missing_required_option(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        # A type whose single variant attribute is required.
        attributes.seed(_attribute("size", AttributeInputType.PLAIN_TEXT, required=True))
        product_types.seed(
            ProductType(
                code=ProductTypeCode("apparel"),
                name="Apparel",
                variant_attributes=(AttributeCode("size"),),
            )
        )
        products.seed(
            Product(
                code=ProductCode("tee"),
                name="Tee",
                product_type=ProductTypeCode("apparel"),
            )
        )

        with pytest.raises(MissingRequiredAttributeError):
            _use_case(variants, products, product_types, attributes, audit).execute(
                _command(product="tee", sku="tee-m")
            )


class TestReads:
    def test_get_returns_the_requested_variant(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _use_case(variants, products, product_types, attributes, audit).execute(_command())

        assert GetVariant(variants).execute(sku="COFFEE-250").sku.value == "COFFEE-250"

    def test_get_raises_when_missing(self, variants: FakeVariantRepository) -> None:
        with pytest.raises(VariantNotFoundError):
            GetVariant(variants).execute(sku="GHOST")

    def test_list_returns_variants_for_an_existing_product(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        create = _use_case(variants, products, product_types, attributes, audit)
        create.execute(_command(sku="coffee-1000", name="1kg Bag"))
        create.execute(_command(sku="coffee-250", name="250g Bag"))

        listed = ListProductVariants(variants, products).execute(product_code="house-blend")

        assert [v.sku.value for v in listed] == ["COFFEE-1000", "COFFEE-250"]

    def test_list_raises_for_an_unknown_product(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
    ) -> None:
        with pytest.raises(ProductNotFoundError):
            ListProductVariants(variants, products).execute(product_code="ghost")
