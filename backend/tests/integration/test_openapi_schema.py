"""The generated OpenAPI schema must document error responses, not just success.

A typed client is only as honest as the schema: if 400/404/409/503 are missing,
consumers cannot model failure. These tests pin the documented status codes.
"""

from __future__ import annotations

from drf_spectacular.generators import SchemaGenerator


def _responses(path: str, method: str) -> dict:
    schema = SchemaGenerator().get_schema(request=None, public=True)
    return schema["paths"][path][method]["responses"]


def test_create_channel_documents_validation_conflict_and_forbidden() -> None:
    responses = _responses("/api/v1/channels/", "post")

    assert "201" in responses
    assert "400" in responses
    assert "403" in responses
    assert "409" in responses


def test_get_channel_documents_not_found() -> None:
    responses = _responses("/api/v1/channels/{slug}/", "get")

    assert "200" in responses
    assert "404" in responses


def test_patch_channel_documents_validation_forbidden_and_not_found() -> None:
    responses = _responses("/api/v1/channels/{slug}/", "patch")

    assert "200" in responses
    assert "400" in responses
    assert "403" in responses
    assert "404" in responses


def test_health_documents_service_unavailable() -> None:
    responses = _responses("/api/v1/health/", "get")

    assert "200" in responses
    assert "503" in responses


def test_login_documents_validation_and_rejection() -> None:
    responses = _responses("/api/v1/auth/login/", "post")

    assert "200" in responses
    assert "400" in responses
    assert "401" in responses


def test_cookie_auth_is_a_documented_security_scheme() -> None:
    schema = SchemaGenerator().get_schema(request=None, public=True)

    assert "cookieAuth" in schema["components"]["securitySchemes"]


def test_request_otp_documents_acceptance_and_validation() -> None:
    responses = _responses("/api/v1/auth/otp/request/", "post")

    assert "202" in responses
    assert "400" in responses


def test_register_documents_creation_and_validation() -> None:
    responses = _responses("/api/v1/auth/register/", "post")

    assert "201" in responses
    assert "400" in responses


def test_password_reset_documents_success_and_validation() -> None:
    responses = _responses("/api/v1/auth/password-reset/", "post")

    assert "200" in responses
    assert "400" in responses


def test_create_attribute_documents_validation_conflict_and_forbidden() -> None:
    responses = _responses("/api/v1/catalog/attributes/", "post")

    assert "201" in responses
    assert "400" in responses
    assert "403" in responses
    assert "409" in responses


def test_get_attribute_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/attributes/{code}/", "get")

    assert "200" in responses
    assert "404" in responses


def test_create_product_type_documents_validation_conflict_and_forbidden() -> None:
    responses = _responses("/api/v1/catalog/product-types/", "post")

    assert "201" in responses
    assert "400" in responses
    assert "403" in responses
    assert "409" in responses


def test_get_product_type_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/product-types/{code}/", "get")

    assert "200" in responses
    assert "404" in responses


def test_create_product_documents_validation_conflict_and_forbidden() -> None:
    responses = _responses("/api/v1/catalog/products/", "post")

    assert "201" in responses
    assert "400" in responses
    assert "403" in responses
    assert "409" in responses


def test_get_product_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/products/{code}/", "get")

    assert "200" in responses
    assert "404" in responses


def test_create_variant_documents_validation_conflict_and_forbidden() -> None:
    responses = _responses("/api/v1/catalog/products/{code}/variants/", "post")

    assert "201" in responses
    assert "400" in responses
    assert "403" in responses
    assert "404" in responses
    assert "409" in responses


def test_get_variant_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/variants/{sku}/", "get")

    assert "200" in responses
    assert "404" in responses


def test_create_category_documents_validation_conflict_and_forbidden() -> None:
    responses = _responses("/api/v1/catalog/categories/", "post")

    assert "201" in responses
    assert "400" in responses
    assert "403" in responses
    assert "409" in responses


def test_get_category_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/categories/{slug}/", "get")

    assert "200" in responses
    assert "404" in responses


def test_create_collection_documents_validation_conflict_and_forbidden() -> None:
    responses = _responses("/api/v1/catalog/collections/", "post")

    assert "201" in responses
    assert "400" in responses
    assert "403" in responses
    assert "409" in responses


def test_get_collection_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/collections/{slug}/", "get")

    assert "200" in responses
    assert "404" in responses


def test_set_collection_products_documents_validation_forbidden_and_not_found() -> None:
    responses = _responses("/api/v1/catalog/collections/{slug}/products/", "put")

    assert "200" in responses
    assert "400" in responses
    assert "403" in responses
    assert "404" in responses


def test_get_collection_products_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/collections/{slug}/products/", "get")

    assert "200" in responses
    assert "404" in responses


def test_set_collection_rule_documents_validation_forbidden_and_not_found() -> None:
    responses = _responses("/api/v1/catalog/collections/{slug}/rule/", "put")

    assert "200" in responses
    assert "400" in responses
    assert "403" in responses
    assert "404" in responses


def test_get_collection_rule_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/collections/{slug}/rule/", "get")

    assert "200" in responses
    assert "404" in responses


def test_get_collection_rule_members_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/collections/{slug}/rule/members/", "get")

    assert "200" in responses
    assert "404" in responses


def test_set_variant_prices_documents_validation_forbidden_and_not_found() -> None:
    responses = _responses("/api/v1/catalog/variants/{sku}/prices/", "put")

    assert "200" in responses
    assert "400" in responses
    assert "403" in responses
    assert "404" in responses


def test_get_variant_prices_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/variants/{sku}/prices/", "get")

    assert "200" in responses
    assert "404" in responses


def test_set_product_categories_documents_validation_forbidden_and_not_found() -> None:
    responses = _responses("/api/v1/catalog/products/{code}/categories/", "put")

    assert "200" in responses
    assert "400" in responses
    assert "403" in responses
    assert "404" in responses


def test_get_product_categories_documents_not_found() -> None:
    responses = _responses("/api/v1/catalog/products/{code}/categories/", "get")

    assert "200" in responses
    assert "404" in responses
