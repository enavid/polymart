/**
 * Typed catalog API module (Phase 2).
 *
 * Mirrors the backend catalog endpoints one-to-one so UI components never touch
 * raw fetch or response shapes. Management reads/writes go through the JSON client
 * (cookie-JWT, credentials:'include'); the two file-oriented endpoints (CSV export
 * download and multipart import) need their own helpers and live at the bottom.
 */

import {
  API_BASE_URL,
  ApiError,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  toQuery,
} from "@/lib/api/client";

// --- Attributes -----------------------------------------------------------

/** A dynamic attribute's input type (drives the value editor). */
export type AttributeInputType = "plain_text" | "number" | "boolean" | "dropdown";

export const ATTRIBUTE_INPUT_TYPES: readonly AttributeInputType[] = [
  "plain_text",
  "number",
  "boolean",
  "dropdown",
];

export interface AttributeChoice {
  value: string;
  label: string;
}

export interface Attribute {
  id: number;
  code: string;
  name: string;
  input_type: AttributeInputType;
  required: boolean;
  choices: AttributeChoice[];
}

export interface CreateAttributeInput {
  code: string;
  name: string;
  input_type: AttributeInputType;
  required?: boolean;
  choices?: AttributeChoice[];
}

export function listAttributes(): Promise<Attribute[]> {
  return apiGet<Attribute[]>("/catalog/attributes/");
}

export function createAttribute(input: CreateAttributeInput): Promise<Attribute> {
  return apiPost<Attribute>("/catalog/attributes/", input);
}

// --- Product types --------------------------------------------------------

export interface ProductType {
  id: number;
  code: string;
  name: string;
  attributes: string[];
  variant_attributes: string[];
}

export interface CreateProductTypeInput {
  code: string;
  name: string;
  attributes?: string[];
  variant_attributes?: string[];
}

export function listProductTypes(): Promise<ProductType[]> {
  return apiGet<ProductType[]>("/catalog/product-types/");
}

export function createProductType(input: CreateProductTypeInput): Promise<ProductType> {
  return apiPost<ProductType>("/catalog/product-types/", input);
}

// --- Products -------------------------------------------------------------

export interface AttributeValue {
  attribute: string;
  value: string;
}

export interface Product {
  id: number;
  code: string;
  name: string;
  product_type: string;
  values: AttributeValue[];
  metadata: Record<string, string>;
  is_published: boolean;
}

export interface CreateProductInput {
  code: string;
  name: string;
  product_type: string;
  values?: AttributeValue[];
  metadata?: Record<string, string>;
}

export function listProducts(): Promise<Product[]> {
  return apiGet<Product[]>("/catalog/products/");
}

export function createProduct(input: CreateProductInput): Promise<Product> {
  return apiPost<Product>("/catalog/products/", input);
}

export function getProduct(code: string): Promise<Product> {
  return apiGet<Product>(`/catalog/products/${code}/`);
}

export function setProductPublished(code: string, isPublished: boolean): Promise<Product> {
  return apiPut<Product>(`/catalog/products/${code}/publication/`, {
    is_published: isPublished,
  });
}

// --- Product <-> category membership --------------------------------------

export function getProductCategories(code: string): Promise<string[]> {
  return apiGet<{ categories: string[] }>(`/catalog/products/${code}/categories/`).then(
    (body) => body.categories,
  );
}

export function setProductCategories(code: string, categories: string[]): Promise<string[]> {
  return apiPut<{ categories: string[] }>(`/catalog/products/${code}/categories/`, {
    categories,
  }).then((body) => body.categories);
}

// --- Variants -------------------------------------------------------------

export interface VariantMedia {
  url: string;
  alt_text: string;
}

export interface Variant {
  id: number;
  product: string;
  sku: string;
  name: string;
  values: AttributeValue[];
  media: VariantMedia[];
}

export interface CreateVariantInput {
  sku: string;
  name: string;
  values?: AttributeValue[];
  media?: VariantMedia[];
}

export function listProductVariants(code: string): Promise<Variant[]> {
  return apiGet<Variant[]>(`/catalog/products/${code}/variants/`);
}

export function createVariant(code: string, input: CreateVariantInput): Promise<Variant> {
  return apiPost<Variant>(`/catalog/products/${code}/variants/`, input);
}

export function getVariant(sku: string): Promise<Variant> {
  return apiGet<Variant>(`/catalog/variants/${sku}/`);
}

// --- Variant prices (per channel; amount is a Decimal string, never a float) ---

export interface ChannelPrice {
  channel: string;
  amount: string;
  currency: string;
}

export interface ChannelPriceInput {
  channel: string;
  amount: string;
}

export function getVariantPrices(sku: string): Promise<ChannelPrice[]> {
  return apiGet<{ prices: ChannelPrice[] }>(`/catalog/variants/${sku}/prices/`).then(
    (body) => body.prices,
  );
}

export function setVariantPrices(sku: string, prices: ChannelPriceInput[]): Promise<ChannelPrice[]> {
  return apiPut<{ prices: ChannelPrice[] }>(`/catalog/variants/${sku}/prices/`, { prices }).then(
    (body) => body.prices,
  );
}

// --- Variant stock --------------------------------------------------------

export function getVariantStock(sku: string): Promise<number> {
  return apiGet<{ quantity: number }>(`/catalog/variants/${sku}/stock/`).then(
    (body) => body.quantity,
  );
}

export function setVariantStock(sku: string, quantity: number): Promise<number> {
  return apiPut<{ quantity: number }>(`/catalog/variants/${sku}/stock/`, { quantity }).then(
    (body) => body.quantity,
  );
}

export function adjustVariantStock(sku: string, delta: number): Promise<number> {
  return apiPatch<{ quantity: number }>(`/catalog/variants/${sku}/stock/`, { delta }).then(
    (body) => body.quantity,
  );
}

// --- Categories (flat list; `parent` slug is null for a root) -------------

export interface Category {
  id: number;
  slug: string;
  name: string;
  parent: string | null;
}

export interface CreateCategoryInput {
  slug: string;
  name: string;
  parent?: string | null;
}

export function listCategories(): Promise<Category[]> {
  return apiGet<Category[]>("/catalog/categories/");
}

export function createCategory(input: CreateCategoryInput): Promise<Category> {
  return apiPost<Category>("/catalog/categories/", input);
}

// --- Collections ----------------------------------------------------------

export interface Collection {
  id: number;
  slug: string;
  name: string;
}

export interface CreateCollectionInput {
  slug: string;
  name: string;
}

export function listCollections(): Promise<Collection[]> {
  return apiGet<Collection[]>("/catalog/collections/");
}

export function createCollection(input: CreateCollectionInput): Promise<Collection> {
  return apiPost<Collection>("/catalog/collections/", input);
}

export function getCollectionProducts(slug: string): Promise<string[]> {
  return apiGet<{ products: string[] }>(`/catalog/collections/${slug}/products/`).then(
    (body) => body.products,
  );
}

export function setCollectionProducts(slug: string, products: string[]): Promise<string[]> {
  return apiPut<{ products: string[] }>(`/catalog/collections/${slug}/products/`, {
    products,
  }).then((body) => body.products);
}

// --- Rule-based collections ----------------------------------------------

export type RuleOperator = "equals" | "not_equals";

export const RULE_OPERATORS: readonly RuleOperator[] = ["equals", "not_equals"];

export interface RuleCondition {
  attribute: string;
  operator: RuleOperator;
  value: string;
}

export function getCollectionRule(slug: string): Promise<RuleCondition[]> {
  return apiGet<{ conditions: RuleCondition[] }>(`/catalog/collections/${slug}/rule/`).then(
    (body) => body.conditions,
  );
}

export function setCollectionRule(slug: string, conditions: RuleCondition[]): Promise<RuleCondition[]> {
  return apiPut<{ conditions: RuleCondition[] }>(`/catalog/collections/${slug}/rule/`, {
    conditions,
  }).then((body) => body.conditions);
}

export function getCollectionRuleMembers(slug: string): Promise<string[]> {
  return apiGet<{ products: string[] }>(`/catalog/collections/${slug}/rule/members/`).then(
    (body) => body.products,
  );
}

// --- Storefront (public read API) -----------------------------------------

export interface StorefrontProduct {
  code: string;
  name: string;
  product_type: string;
  values: AttributeValue[];
  metadata: Record<string, string>;
  // The product's primary image (promoted from a variant), or null when it has
  // none -- the storefront then falls back to a monogram placeholder.
  image?: VariantMedia | null;
  // Present only when the list was requested for a channel. `from_price` is an
  // exact string (the lowest in-channel variant price) or null when unpriced.
  from_price?: string | null;
  currency?: string | null;
  available?: boolean;
}

export interface StorefrontProductPage {
  count: number;
  limit: number;
  offset: number;
  results: StorefrontProduct[];
}

export interface StorefrontFilters {
  search?: string;
  category?: string;
  collection?: string;
  product_type?: string;
  channel?: string;
  limit?: number;
  offset?: number;
}

export function listStorefrontProducts(
  filters: StorefrontFilters = {},
): Promise<StorefrontProductPage> {
  return apiGet<StorefrontProductPage>(
    `/catalog/storefront/products/${toQuery({
      search: filters.search,
      category: filters.category,
      collection: filters.collection,
      product_type: filters.product_type,
      channel: filters.channel,
      limit: filters.limit,
      offset: filters.offset,
    })}`,
  );
}

export function getStorefrontProduct(code: string): Promise<StorefrontProduct> {
  return apiGet<StorefrontProduct>(`/catalog/storefront/products/${code}/`);
}

// --- Storefront taxonomy (public; powers the PLP filter choosers) ---------

export interface StorefrontCategory {
  slug: string;
  name: string;
  parent: string | null;
}

export interface StorefrontCollection {
  slug: string;
  name: string;
}

export interface StorefrontProductType {
  code: string;
  name: string;
}

export function listStorefrontCategories(): Promise<StorefrontCategory[]> {
  return apiGet<StorefrontCategory[]>("/catalog/storefront/categories/");
}

export function listStorefrontCollections(): Promise<StorefrontCollection[]> {
  return apiGet<StorefrontCollection[]>("/catalog/storefront/collections/");
}

export function listStorefrontProductTypes(): Promise<StorefrontProductType[]> {
  return apiGet<StorefrontProductType[]>("/catalog/storefront/product-types/");
}

/** A variant's storefront price. `amount` is an exact string (never a float). */
export interface StorefrontVariantPrice {
  amount: string;
  currency: string;
}

/** A published product's variant as offered on the storefront (its purchasable unit). */
export interface StorefrontVariant {
  sku: string;
  name: string;
  values: AttributeValue[];
  media: VariantMedia[];
  /** The base price in the requested channel, or `null` if it has none there. */
  price: StorefrontVariantPrice | null;
}

export interface StorefrontProductVariants {
  channel: string;
  variants: StorefrontVariant[];
}

/** List a published product's purchasable variants, priced for one channel. */
export function getStorefrontProductVariants(
  code: string,
  channel: string,
): Promise<StorefrontProductVariants> {
  return apiGet<StorefrontProductVariants>(
    `/catalog/storefront/products/${code}/variants/${toQuery({ channel })}`,
  );
}

// --- CSV import / export --------------------------------------------------

export interface ImportRowError {
  row_number: number;
  code: string;
  error: string;
}

export interface ProductImportResult {
  created: number;
  errors: ImportRowError[];
}

/** Fetch the products CSV and trigger a browser download (authenticated). */
export async function downloadProductsCsv(filename = "products.csv"): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/catalog/products/export/`, {
    method: "GET",
    headers: { Accept: "text/csv" },
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(response.status, `export failed with status ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * Upload a CSV file for bulk import. The endpoint always returns the import-result
 * shape (200 when all rows are created, 400 when none are), so a 400 carries the
 * per-row errors rather than being a transport failure — we parse both alike.
 */
export async function importProductsCsv(file: File): Promise<ProductImportResult> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE_URL}/catalog/products/import/`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    body: form,
  });
  if (response.status === 200 || response.status === 400) {
    return (await response.json()) as ProductImportResult;
  }
  throw new ApiError(response.status, `import failed with status ${response.status}`);
}
