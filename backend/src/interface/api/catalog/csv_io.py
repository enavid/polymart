"""CSV codec for product import/export (the transport format, at the edge).

Turning products into CSV text and back is a transport detail, so it lives in the
interface layer: the use cases speak only in ``ProductRow`` objects. The codec is
deliberately dumb about *meaning* -- it maps cells to/from fields and raises only on
a structurally unusable file (a missing required column). All row-level semantics
(valid code, known product type, attribute conformance) are the use case's.

Column layout: the fixed ``code,name,product_type,is_published,categories`` columns
followed by one ``attr:<code>`` column per attribute seen across the rows. Category
slugs share a cell, joined by ``|``. ``is_published`` is parsed leniently and
fail-closed: only a clearly truthy token publishes; anything else stays a draft.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from src.application.catalog.use_cases import AttributeValueInput, ProductRow

# Fixed columns, then dynamic ``attr:<code>`` columns.
_CODE = "code"
_NAME = "name"
_PRODUCT_TYPE = "product_type"
_IS_PUBLISHED = "is_published"
_CATEGORIES = "categories"
_FIXED_COLUMNS = (_CODE, _NAME, _PRODUCT_TYPE, _IS_PUBLISHED, _CATEGORIES)
_REQUIRED_COLUMNS = (_CODE, _NAME, _PRODUCT_TYPE)
_ATTRIBUTE_PREFIX = "attr:"
# Category slugs share one cell, separated by a character a slug never contains.
_CATEGORY_SEPARATOR = "|"
# Tokens that publish a product; everything else (including blank) stays a draft.
_TRUE_TOKENS = frozenset({"true", "1", "yes"})


class CsvFormatError(Exception):
    """Raised when an upload is not a usable products CSV (e.g. a missing column)."""


def _attribute_codes(rows: Sequence[ProductRow]) -> list[str]:
    """The sorted union of attribute codes across all rows (deterministic columns)."""
    codes: set[str] = set()
    for row in rows:
        codes.update(value.attribute for value in row.values)
    return sorted(codes)


def encode_products(rows: Sequence[ProductRow]) -> str:
    """Encode product rows as CSV text (header + one line per product)."""
    attribute_codes = _attribute_codes(rows)
    header = [*_FIXED_COLUMNS, *(f"{_ATTRIBUTE_PREFIX}{code}" for code in attribute_codes)]

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        by_code = {value.attribute: value.value for value in row.values}
        writer.writerow(
            [
                row.code,
                row.name,
                row.product_type,
                "true" if row.is_published else "false",
                _CATEGORY_SEPARATOR.join(row.categories),
                *(by_code.get(code, "") for code in attribute_codes),
            ]
        )
    return buffer.getvalue()


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in _TRUE_TOKENS


def _parse_categories(raw: str) -> tuple[str, ...]:
    return tuple(slug.strip() for slug in raw.split(_CATEGORY_SEPARATOR) if slug.strip())


def _parse_values(row: dict[str, str | None]) -> tuple[AttributeValueInput, ...]:
    values = []
    for column, cell in row.items():
        if column and column.startswith(_ATTRIBUTE_PREFIX) and cell and cell.strip():
            code = column[len(_ATTRIBUTE_PREFIX) :]
            values.append(AttributeValueInput(attribute=code, value=cell))
    return tuple(values)


def decode_products(text: str) -> list[ProductRow]:
    """Decode CSV text into product rows, or raise ``CsvFormatError`` if unusable."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CsvFormatError("the file is empty")
    missing = [column for column in _REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing:
        raise CsvFormatError(f"missing required column(s): {', '.join(missing)}")

    return [
        ProductRow(
            code=(row.get(_CODE) or "").strip(),
            name=(row.get(_NAME) or "").strip(),
            product_type=(row.get(_PRODUCT_TYPE) or "").strip(),
            is_published=_parse_bool(row.get(_IS_PUBLISHED) or ""),
            categories=_parse_categories(row.get(_CATEGORIES) or ""),
            values=_parse_values(row),
        )
        for row in reader
    ]
