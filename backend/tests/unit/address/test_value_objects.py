"""Unit tests for the address value objects (pure, no framework)."""

from __future__ import annotations

import pytest

from src.domain.address.exceptions import (
    InvalidAddressIdError,
    InvalidAddressLineError,
    InvalidCityError,
    InvalidPhoneNumberError,
    InvalidPostalCodeError,
    InvalidProvinceError,
    InvalidRecipientNameError,
)
from src.domain.address.value_objects import (
    AddressId,
    AddressLine,
    City,
    PhoneNumber,
    PostalCode,
    Province,
    RecipientName,
)


class TestRecipientName:
    def test_strips_surrounding_whitespace(self) -> None:
        assert RecipientName("  Sara Ahmadi  ").value == "Sara Ahmadi"

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 201])
    def test_rejects_blank_or_too_long(self, bad: str) -> None:
        with pytest.raises(InvalidRecipientNameError):
            RecipientName(bad)


class TestPhoneNumber:
    @pytest.mark.parametrize(
        "raw",
        ["09123456789", "+989123456789", "00989123456789", "9123456789", "0912 345 6789"],
    )
    def test_accepts_the_common_spellings(self, raw: str) -> None:
        assert PhoneNumber(raw).value == "+989123456789"

    @pytest.mark.parametrize("bad", ["", "12345", "08123456789", "+981234567890", "not-a-number"])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidPhoneNumberError):
            PhoneNumber(bad)


class TestProvince:
    def test_strips_surrounding_whitespace(self) -> None:
        assert Province("  Tehran  ").value == "Tehran"

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 101])
    def test_rejects_blank_or_too_long(self, bad: str) -> None:
        with pytest.raises(InvalidProvinceError):
            Province(bad)


class TestCity:
    def test_strips_surrounding_whitespace(self) -> None:
        assert City("  Tehran  ").value == "Tehran"

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 101])
    def test_rejects_blank_or_too_long(self, bad: str) -> None:
        with pytest.raises(InvalidCityError):
            City(bad)


class TestPostalCode:
    def test_accepts_ten_digits(self) -> None:
        assert PostalCode("1234567890").value == "1234567890"

    def test_strips_separators(self) -> None:
        assert PostalCode("12345-67890").value == "1234567890"

    @pytest.mark.parametrize("bad", ["", "123456789", "12345678901", "123456789a"])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidPostalCodeError):
            PostalCode(bad)


class TestAddressLine:
    def test_strips_surrounding_whitespace(self) -> None:
        assert AddressLine("  Valiasr St, No. 1  ").value == "Valiasr St, No. 1"

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 256])
    def test_rejects_blank_or_too_long(self, bad: str) -> None:
        with pytest.raises(InvalidAddressLineError):
            AddressLine(bad)


class TestAddressId:
    def test_canonicalises_to_upper_case(self) -> None:
        assert AddressId("addr-abc123").value == "ADDR-ABC123"

    @pytest.mark.parametrize("bad", ["", "short", "addr abc", "x" * 41, "addr_1"])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidAddressIdError):
            AddressId(bad)
