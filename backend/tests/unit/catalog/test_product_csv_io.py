"""Unit tests for the product CSV codec (rows <-> CSV text; no DB, no HTTP)."""

from __future__ import annotations

import pytest

from src.application.catalog.use_cases import AttributeValueInput, ProductRow
from src.interface.api.catalog.csv_io import CsvFormatError, decode_products, encode_products


def _row(
    code: str,
    *,
    name: str | None = None,
    product_type: str = "coffee",
    is_published: bool = False,
    categories: tuple[str, ...] = (),
    values: tuple[AttributeValueInput, ...] = (),
) -> ProductRow:
    return ProductRow(
        code=code,
        name=name if name is not None else code.title(),
        product_type=product_type,
        is_published=is_published,
        categories=categories,
        values=values,
    )


class TestEncode:
    def test_header_lists_fixed_columns_then_sorted_attribute_columns(self) -> None:
        rows = (
            _row("a", values=(AttributeValueInput(attribute="roast", value="dark"),)),
            _row("b", values=(AttributeValueInput(attribute="origin", value="peru"),)),
        )

        header = encode_products(rows).splitlines()[0]

        assert header == "code,name,product_type,is_published,categories,attr:origin,attr:roast"

    def test_emits_one_row_per_product_with_pipe_joined_categories(self) -> None:
        rows = (
            _row(
                "house-blend",
                name="House Blend",
                is_published=True,
                categories=("espresso", "decaf"),
            ),
        )

        body = encode_products(rows).splitlines()[1]

        assert body == "house-blend,House Blend,coffee,true,espresso|decaf"

    def test_with_no_products_emits_only_the_header(self) -> None:
        text = encode_products(())

        assert text.splitlines() == ["code,name,product_type,is_published,categories"]


class TestDecode:
    def test_parses_a_minimal_row(self) -> None:
        text = "code,name,product_type\nhouse-blend,House Blend,coffee\n"

        rows = decode_products(text)

        assert rows == [
            ProductRow(
                code="house-blend",
                name="House Blend",
                product_type="coffee",
                is_published=False,
                categories=(),
                values=(),
            )
        ]

    def test_round_trips_through_encode(self) -> None:
        original = (
            _row(
                "house-blend",
                is_published=True,
                categories=("espresso", "decaf"),
                values=(AttributeValueInput(attribute="origin", value="ethiopia"),),
            ),
            _row("cold-brew"),
        )

        assert decode_products(encode_products(original)) == list(original)

    def test_missing_a_required_column_is_a_format_error(self) -> None:
        with pytest.raises(CsvFormatError):
            decode_products("code,name\nhouse-blend,House Blend\n")

    def test_an_empty_file_is_a_format_error(self) -> None:
        with pytest.raises(CsvFormatError):
            decode_products("")

    @pytest.mark.parametrize("token", ["true", "TRUE", "1", "yes", "Yes"])
    def test_truthy_published_tokens(self, token: str) -> None:
        text = f"code,name,product_type,is_published\nx,X,coffee,{token}\n"

        assert decode_products(text)[0].is_published is True

    @pytest.mark.parametrize("token", ["false", "0", "no", "", "garbage"])
    def test_other_published_tokens_are_false(self, token: str) -> None:
        # Lenient + fail-closed: anything not clearly truthy means unpublished.
        text = f"code,name,product_type,is_published\nx,X,coffee,{token}\n"

        assert decode_products(text)[0].is_published is False

    def test_splits_categories_and_drops_blanks(self) -> None:
        text = "code,name,product_type,categories\nx,X,coffee,espresso||decaf\n"

        assert decode_products(text)[0].categories == ("espresso", "decaf")

    def test_ignores_empty_attribute_cells(self) -> None:
        text = "code,name,product_type,attr:origin,attr:roast\nx,X,coffee,peru,\n"

        values = decode_products(text)[0].values

        assert [(v.attribute, v.value) for v in values] == [("origin", "peru")]
