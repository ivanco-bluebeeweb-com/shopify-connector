"""Chat functions for Shopify Connector: connection management, products/
variants/media/collections, orders/draft orders/refunds/fulfillment,
customers, inventory/locations, discounts, metafields, webhooks, bulk
operations, and value-add reports (Tier 3). Built on shopify_client.py /
schemas.py, following the same shape as MuleSoft Connector's handlers.py.
"""
from __future__ import annotations

import json
import uuid

from imperal_sdk import ActionResult

import shopify_client as sc
from app import ext, chat
from schemas import (
    NoParams,
    ConnectShopifyParams, ProviderConnection, ProviderConnectionList,
    DisconnectShopifyParams, DeleteResult, ListConnectionsParams,
    Product, ProductVariant, ProductList, ListProductsParams, GetProductParams,
    CreateProductParams, UpdateProductParams, DeleteProductParams,
    CreateProductVariantParams, UpdateProductVariantParams, DeleteProductVariantParams,
    UploadProductMediaParams,
    Collection, CollectionList, ListCollectionsParams, CreateCollectionParams,
    AddProductsToCollectionParams, RemoveProductsFromCollectionParams,
    OrderLineItem, Order, OrderList, ListOrdersParams, GetOrderParams,
    CancelOrderParams, UpdateOrderNoteParams,
    CreateDraftOrderParams, CompleteDraftOrderParams, RefundOrderParams,
    FulfillmentOrderRef, ListFulfillmentOrdersParams, FulfillmentOrderList,
    CreateFulfillmentParams, CancelFulfillmentParams,
    Customer, CustomerList, ListCustomersParams, GetCustomerParams,
    CreateCustomerParams, UpdateCustomerParams, DeleteCustomerParams,
    Location, LocationList, ListLocationsParams,
    InventoryLevel, InventoryLevelList, GetInventoryLevelsParams,
    SetInventoryQuantityParams, AdjustInventoryQuantityParams,
    Discount, DiscountList, ListDiscountsParams, CreateCodeDiscountParams,
    CreateAutomaticDiscountParams, DeleteDiscountParams,
    Metafield, MetafieldList, ListMetafieldsParams, SetMetafieldParams, DeleteMetafieldParams,
    WebhookSubscription, WebhookList, ListWebhooksParams, CreateWebhookParams, DeleteWebhookParams,
    RunBulkQueryParams, BulkOperationStatus, GetBulkOperationStatusParams, CancelBulkOperationParams,
    LowStockRow, LowStockReport, GetLowStockReportParams,
    StoreSummary, GetStoreSummaryParams,
)

_SECRET_NAME = "shopify_connections"


# ──────────────────────────────────────────────────────────────────────────
# Connection storage helpers
# ──────────────────────────────────────────────────────────────────────────


async def _load_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_SECRET_NAME)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data if isinstance(data, list) else []


async def _save_connections(ctx, connections: list[dict]) -> None:
    await ctx.secrets.set(_SECRET_NAME, json.dumps(connections))


async def _resolve_or_error(ctx, connection_id: str):
    connections = await _load_connections(ctx)
    if not connections:
        return None, None, ActionResult.error(
            "No Shopify store connected yet. Use connect_shopify first.",
            code="not_connected",
        )
    if connection_id:
        for c in connections:
            if c.get("id") == connection_id:
                return c, c.get("access_token", ""), None
        return None, None, ActionResult.error(
            f"No connected store with connection_id '{connection_id}'.", code="not_found",
        )
    if len(connections) > 1:
        return None, None, ActionResult.error(
            "Multiple stores connected -- pass connection_id to pick one (see list_connections).",
            code="ambiguous",
        )
    c = connections[0]
    return c, c.get("access_token", ""), None


def _conn_to_entity(c: dict) -> ProviderConnection:
    return ProviderConnection(
        id=c.get("id", ""),
        title=c.get("label") or c.get("shop_domain", ""),
        connected=True,
        detail=c.get("shop_domain", ""),
        shop_domain=c.get("shop_domain", ""),
    )


# ──────────────────────────────────────────────────────────────────────────
# Connection management
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "connect_shopify",
    "Connect a Shopify store by its *.myshopify.com domain and a Custom App Admin API access token, after checking the token actually works.",
    action_type="write",
    chain_callable=True,
    data_model=ProviderConnection,
    event="shopify-connector.connect_shopify",
    effects=["shopify.connection.created"],
)
async def connect_shopify(ctx, params: ConnectShopifyParams) -> ActionResult:
    """Validate the token against the shop and store the connection."""
    shop_domain = params.shop_domain.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
    if not shop_domain:
        return ActionResult.error("shop_domain is required.", code="bad_request")
    if not params.access_token:
        return ActionResult.error("access_token is required.", code="bad_request")
    try:
        data = await sc.graphql(ctx, params.access_token, shop_domain, "query { shop { name myshopifyDomain } }")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    shop_name = (data.get("shop") or {}).get("name", shop_domain)
    connections = await _load_connections(ctx)
    conn_id = str(uuid.uuid4())
    connections.append({
        "id": conn_id,
        "shop_domain": shop_domain,
        "access_token": params.access_token,
        "label": params.label or shop_name,
    })
    await _save_connections(ctx, connections)
    return ActionResult.ok(ProviderConnection(
        id=conn_id, title=params.label or shop_name, connected=True,
        detail=shop_domain, shop_domain=shop_domain,
    ), summary=f"Connected Shopify store '{shop_name}' ({shop_domain}).")


@chat.function(
    "disconnect_shopify",
    "Disconnect a Shopify store: deletes the saved access token. Existing data in Shopify itself is untouched.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="shopify-connector.disconnect_shopify",
    effects=["shopify.connection.deleted"],
)
async def disconnect_shopify(ctx, params: DisconnectShopifyParams) -> ActionResult:
    """Remove one saved store connection."""
    connections = await _load_connections(ctx)
    remaining = [c for c in connections if c.get("id") != params.connection_id]
    if len(remaining) == len(connections):
        return ActionResult.error(f"No connection with id '{params.connection_id}'.", code="not_found")
    await _save_connections(ctx, remaining)
    return ActionResult.ok(DeleteResult(deleted=True, id=params.connection_id), summary="Store disconnected.")


@chat.function(
    "list_connections",
    "List the connected Shopify stores.",
    action_type="read",
    chain_callable=True,
    data_model=ProviderConnectionList,
    event="shopify-connector.list_connections",
)
async def list_connections(ctx, params: ListConnectionsParams) -> ActionResult:
    """List saved store connections."""
    connections = await _load_connections(ctx)
    items = [_conn_to_entity(c) for c in connections]
    return ActionResult.ok(ProviderConnectionList(items=items), summary=f"{len(items)} store(s) connected.")


# ──────────────────────────────────────────────────────────────────────────
# Products / Variants / Media
# ──────────────────────────────────────────────────────────────────────────


def _variant_to_entity(v: dict) -> ProductVariant:
    inv = v.get("inventoryItem") or {}
    levels = ((inv.get("inventoryLevels") or {}).get("edges") or [])
    qty = 0
    if levels:
        qty = sum((lv.get("node", {}).get("quantities") or [{}])[0].get("quantity", 0) for lv in levels)
    return ProductVariant(
        id=v.get("id", ""), title=v.get("title", ""), sku=v.get("sku", "") or "",
        price=str(v.get("price", "")), compare_at_price=str(v.get("compareAtPrice") or ""),
        inventory_quantity=v.get("inventoryQuantity", 0) or 0,
        inventory_item_id=inv.get("id", ""),
    )


def _product_to_entity(p: dict) -> Product:
    variants = [_variant_to_entity(e.get("node", {})) for e in (p.get("variants", {}).get("edges") or [])]
    featured = (p.get("featuredImage") or {}).get("url", "")
    return Product(
        id=p.get("id", ""), title=p.get("title", ""), handle=p.get("handle", ""),
        status=p.get("status", ""), vendor=p.get("vendor", "") or "",
        product_type=p.get("productType", "") or "", tags=p.get("tags") or [],
        variants=variants, featured_image=featured,
        created_at=p.get("createdAt", ""), updated_at=p.get("updatedAt", ""),
    )


_PRODUCT_FIELDS = """
  id title handle status vendor productType tags createdAt updatedAt
  featuredImage { url }
  variants(first: 25) {
    edges { node { id title sku price compareAtPrice inventoryQuantity inventoryItem { id } } }
  }
"""


@chat.function(
    "list_products",
    "List products in the connected store, with variants, price, and stock. Supports Shopify search syntax and pagination.",
    action_type="read",
    chain_callable=True,
    data_model=ProductList,
    event="shopify-connector.list_products",
)
async def list_products(ctx, params: ListProductsParams) -> ActionResult:
    """List products, optionally filtered/paginated."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = f"""
    query($first: Int!, $after: String, $q: String) {{
      products(first: $first, after: $after, query: $q) {{
        edges {{ node {{ {_PRODUCT_FIELDS} }} }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {
            "first": params.limit, "after": params.after or None, "q": params.query or None,
        })
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    conn_data = data.get("products", {})
    items = [_product_to_entity(e["node"]) for e in conn_data.get("edges", [])]
    page = conn_data.get("pageInfo", {})
    return ActionResult.ok(
        ProductList(items=items, has_next_page=page.get("hasNextPage", False), end_cursor=page.get("endCursor", "")),
        summary=f"{len(items)} product(s).",
    )


@chat.function(
    "get_product",
    "Read one product in full, including its variants, price, and stock.",
    action_type="read",
    chain_callable=True,
    data_model=Product,
    event="shopify-connector.get_product",
)
async def get_product(ctx, params: GetProductParams) -> ActionResult:
    """Read one product by GID."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = f"query($id: ID!) {{ product(id: $id) {{ {_PRODUCT_FIELDS} }} }}"
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {"id": params.product_id})
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data.get("product")
    if not node:
        return ActionResult.error(f"No product with id '{params.product_id}'.", code="not_found")
    return ActionResult.ok(_product_to_entity(node), summary=f"Product '{node.get('title', '')}'.")


@chat.function(
    "create_product",
    "Create a new product (title, description, vendor, type, tags, status). Starts with no variants -- add them with create_product_variant.",
    action_type="write",
    chain_callable=True,
    data_model=Product,
    event="shopify-connector.create_product",
    effects=["shopify.product.created"],
)
async def create_product(ctx, params: CreateProductParams) -> ActionResult:
    """Create a product shell."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = f"""
    mutation($input: ProductInput!) {{
      productCreate(input: $input) {{
        product {{ {_PRODUCT_FIELDS} }}
        userErrors {{ field message }}
      }}
    }}
    """
    input_obj = {
        "title": params.title, "descriptionHtml": params.description_html,
        "vendor": params.vendor, "productType": params.product_type,
        "tags": params.tags, "status": params.status,
    }
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "productCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data["productCreate"]["product"]
    return ActionResult.ok(_product_to_entity(node), summary=f"Created product '{node.get('title', '')}'.")


@chat.function(
    "update_product",
    "Update selected fields of an existing product. Only given fields change.",
    action_type="write",
    chain_callable=True,
    data_model=Product,
    event="shopify-connector.update_product",
    effects=["shopify.product.updated"],
)
async def update_product(ctx, params: UpdateProductParams) -> ActionResult:
    """Update a product's fields."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    input_obj: dict = {"id": params.product_id}
    if params.title:
        input_obj["title"] = params.title
    if params.description_html:
        input_obj["descriptionHtml"] = params.description_html
    if params.vendor:
        input_obj["vendor"] = params.vendor
    if params.product_type:
        input_obj["productType"] = params.product_type
    if params.status:
        input_obj["status"] = params.status
    if params.tags:
        input_obj["tags"] = params.tags
    mutation = f"""
    mutation($input: ProductInput!) {{
      productUpdate(input: $input) {{
        product {{ {_PRODUCT_FIELDS} }}
        userErrors {{ field message }}
      }}
    }}
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "productUpdate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data["productUpdate"]["product"]
    return ActionResult.ok(_product_to_entity(node), summary=f"Updated product '{node.get('title', '')}'.")


@chat.function(
    "delete_product",
    "Permanently delete a product. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="shopify-connector.delete_product",
    effects=["shopify.product.deleted"],
)
async def delete_product(ctx, params: DeleteProductParams) -> ActionResult:
    """Delete a product permanently."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($input: ProductDeleteInput!) {
      productDelete(input: $input) { deletedProductId userErrors { field message } }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": {"id": params.product_id}})
        sc.raise_for_user_errors(data, "productDelete")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    deleted_id = data["productDelete"].get("deletedProductId", params.product_id)
    return ActionResult.ok(DeleteResult(deleted=True, id=deleted_id), summary="Product deleted.")


@chat.function(
    "create_product_variant",
    "Add a new variant to an existing product.",
    action_type="write",
    chain_callable=True,
    data_model=ProductVariant,
    event="shopify-connector.create_product_variant",
    effects=["shopify.variant.created"],
)
async def create_product_variant(ctx, params: CreateProductVariantParams) -> ActionResult:
    """Create a variant on a product."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    variant_input: dict = {"price": params.price}
    if params.sku:
        variant_input["inventoryItem"] = {"sku": params.sku}
    if params.compare_at_price:
        variant_input["compareAtPrice"] = params.compare_at_price
    if params.option_values:
        variant_input["optionValues"] = [{"name": v} for v in params.option_values]
    mutation = """
    mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkCreate(productId: $productId, variants: $variants) {
        productVariants { id title sku price compareAtPrice inventoryQuantity inventoryItem { id } }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "productId": params.product_id, "variants": [variant_input],
        })
        sc.raise_for_user_errors(data, "productVariantsBulkCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    variants = data["productVariantsBulkCreate"].get("productVariants") or []
    if not variants:
        return ActionResult.error("Shopify did not return the created variant.", code="empty_response")
    return ActionResult.ok(_variant_to_entity(variants[0]), summary="Variant created.")


@chat.function(
    "update_product_variant",
    "Update price, SKU, or compare-at price of an existing variant.",
    action_type="write",
    chain_callable=True,
    data_model=ProductVariant,
    event="shopify-connector.update_product_variant",
    effects=["shopify.variant.updated"],
)
async def update_product_variant(ctx, params: UpdateProductVariantParams) -> ActionResult:
    """Update a variant's price/SKU/compare-at price."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    # productVariantsBulkUpdate needs the parent product id -- fetch it first.
    lookup = "query($id: ID!) { productVariant(id: $id) { id product { id } } }"
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], lookup, {"id": params.variant_id})
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    pv = data.get("productVariant")
    if not pv:
        return ActionResult.error(f"No variant with id '{params.variant_id}'.", code="not_found")
    product_id = pv["product"]["id"]
    variant_input: dict = {"id": params.variant_id}
    if params.price:
        variant_input["price"] = params.price
    if params.compare_at_price:
        variant_input["compareAtPrice"] = params.compare_at_price
    if params.sku:
        variant_input["inventoryItem"] = {"sku": params.sku}
    mutation = """
    mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        productVariants { id title sku price compareAtPrice inventoryQuantity inventoryItem { id } }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "productId": product_id, "variants": [variant_input],
        })
        sc.raise_for_user_errors(data, "productVariantsBulkUpdate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    variants = data["productVariantsBulkUpdate"].get("productVariants") or []
    if not variants:
        return ActionResult.error("Shopify did not return the updated variant.", code="empty_response")
    return ActionResult.ok(_variant_to_entity(variants[0]), summary="Variant updated.")


@chat.function(
    "delete_product_variant",
    "Permanently delete a variant from a product.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="shopify-connector.delete_product_variant",
    effects=["shopify.variant.deleted"],
)
async def delete_product_variant(ctx, params: DeleteProductVariantParams) -> ActionResult:
    """Delete a variant."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($productId: ID!, $variantsIds: [ID!]!) {
      productVariantsBulkDelete(productId: $productId, variantsIds: $variantsIds) {
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "productId": params.product_id, "variantsIds": [params.variant_id],
        })
        sc.raise_for_user_errors(data, "productVariantsBulkDelete")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(DeleteResult(deleted=True, id=params.variant_id), summary="Variant deleted.")


@chat.function(
    "upload_product_media",
    "Attach a publicly reachable image URL to a product's media gallery.",
    action_type="write",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.upload_product_media",
    effects=["shopify.product.media_added"],
)
async def upload_product_media(ctx, params: UploadProductMediaParams) -> ActionResult:
    """Attach an image URL to a product."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($productId: ID!, $media: [CreateMediaInput!]!) {
      productCreateMedia(productId: $productId, media: $media) {
        media { alt mediaContentType status }
        mediaUserErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "productId": params.product_id,
            "media": [{"originalSource": params.image_url, "alt": params.alt_text, "mediaContentType": "IMAGE"}],
        })
        sc.raise_for_user_errors(data, "productCreateMedia", error_field="mediaUserErrors")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary="Image attached to product media.")


# ──────────────────────────────────────────────────────────────────────────
# Collections
# ──────────────────────────────────────────────────────────────────────────


def _collection_to_entity(c: dict) -> Collection:
    return Collection(
        id=c.get("id", ""), title=c.get("title", ""), handle=c.get("handle", ""),
        products_count=(c.get("productsCount") or {}).get("count", 0),
        is_smart=bool(c.get("ruleSet")),
    )


@chat.function(
    "list_collections",
    "List product collections (manual and smart/automated).",
    action_type="read",
    chain_callable=True,
    data_model=CollectionList,
    event="shopify-connector.list_collections",
)
async def list_collections(ctx, params: ListCollectionsParams) -> ActionResult:
    """List collections."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query($first: Int!, $after: String) {
      collections(first: $first, after: $after) {
        edges { node { id title handle productsCount { count } ruleSet { rules { column } } } }
        pageInfo { hasNextPage endCursor }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {
            "first": params.limit, "after": params.after or None,
        })
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    conns = data.get("collections", {})
    items = [_collection_to_entity(e["node"]) for e in conns.get("edges", [])]
    page_info = conns.get("pageInfo", {})
    return ActionResult.ok(
        CollectionList(items=items, has_next_page=page_info.get("hasNextPage", False), end_cursor=page_info.get("endCursor", "")),
        summary=f"{len(items)} collection(s).",
    )


@chat.function(
    "create_collection",
    "Create a manual collection, or a smart/automated collection when rules_json is provided.",
    action_type="write",
    chain_callable=True,
    data_model=Collection,
    event="shopify-connector.create_collection",
    effects=["shopify.collection.created"],
)
async def create_collection(ctx, params: CreateCollectionParams) -> ActionResult:
    """Create a collection."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    input_obj: dict = {"title": params.title}
    if params.description_html:
        input_obj["descriptionHtml"] = params.description_html
    if params.rules_json:
        try:
            rules = json.loads(params.rules_json)
        except Exception:
            return ActionResult.error("rules_json is not valid JSON.", code="bad_request")
        input_obj["ruleSet"] = {"appliedDisjunctively": False, "rules": rules}
    mutation = """
    mutation($input: CollectionInput!) {
      collectionCreate(input: $input) {
        collection { id title handle productsCount { count } ruleSet { rules { column } } }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "collectionCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data["collectionCreate"]["collection"]
    return ActionResult.ok(_collection_to_entity(node), summary=f"Collection '{node.get('title', '')}' created.")


@chat.function(
    "add_products_to_collection",
    "Add products to an existing (manual) collection.",
    action_type="write",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.add_products_to_collection",
    effects=["shopify.collection.updated"],
)
async def add_products_to_collection(ctx, params: AddProductsToCollectionParams) -> ActionResult:
    """Add products to a collection."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($id: ID!, $productIds: [ID!]!) {
      collectionAddProducts(id: $id, productIds: $productIds) {
        collection { id }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "id": params.collection_id, "productIds": params.product_ids,
        })
        sc.raise_for_user_errors(data, "collectionAddProducts")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary=f"Added {len(params.product_ids)} product(s) to collection.")


@chat.function(
    "remove_products_from_collection",
    "Remove products from a collection.",
    action_type="write",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.remove_products_from_collection",
    effects=["shopify.collection.updated"],
)
async def remove_products_from_collection(ctx, params: RemoveProductsFromCollectionParams) -> ActionResult:
    """Remove products from a collection."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($id: ID!, $productIds: [ID!]!) {
      collectionRemoveProducts(id: $id, productIds: $productIds) {
        job { id }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "id": params.collection_id, "productIds": params.product_ids,
        })
        sc.raise_for_user_errors(data, "collectionRemoveProducts")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary=f"Removing {len(params.product_ids)} product(s) from collection (async job).")


# ──────────────────────────────────────────────────────────────────────────
# Orders / Draft Orders / Refunds / Fulfillment
# ──────────────────────────────────────────────────────────────────────────


def _order_to_entity(o: dict) -> Order:
    line_items = [
        OrderLineItem(
            id=e.get("node", {}).get("id", ""),
            title=e.get("node", {}).get("title", ""),
            quantity=e.get("node", {}).get("quantity", 0) or 0,
            sku=e.get("node", {}).get("sku", "") or "",
            price=str((e.get("node", {}).get("originalUnitPriceSet", {}).get("shopMoney", {}) or {}).get("amount", "")),
        )
        for e in (o.get("lineItems", {}).get("edges") or [])
    ]
    return Order(
        id=o.get("id", ""), name=o.get("name", ""), email=o.get("email", "") or "",
        financial_status=o.get("displayFinancialStatus", "") or "",
        fulfillment_status=o.get("displayFulfillmentStatus", "") or "",
        total_price=str((o.get("totalPriceSet", {}).get("shopMoney", {}) or {}).get("amount", "")),
        currency=(o.get("totalPriceSet", {}).get("shopMoney", {}) or {}).get("currencyCode", ""),
        created_at=o.get("createdAt", ""),
        line_items=line_items,
        customer_id=(o.get("customer") or {}).get("id", "") or "",
    )


_ORDER_FIELDS = """
  id name email displayFinancialStatus displayFulfillmentStatus createdAt
  totalPriceSet { shopMoney { amount currencyCode } }
  customer { id }
  lineItems(first: 25) {
    edges { node { id title quantity sku originalUnitPriceSet { shopMoney { amount } } } }
  }
"""


@chat.function(
    "list_orders",
    "List orders in the connected store, with financial/fulfillment status, totals, and line items. Supports Shopify search syntax and pagination.",
    action_type="read",
    chain_callable=True,
    data_model=OrderList,
    event="shopify-connector.list_orders",
)
async def list_orders(ctx, params: ListOrdersParams) -> ActionResult:
    """List orders."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = f"""
    query($first: Int!, $after: String, $query: String) {{
      orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT, reverse: true) {{
        pageInfo {{ hasNextPage endCursor }}
        edges {{ node {{ {_ORDER_FIELDS} }} }}
      }}
    }}
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {
            "first": params.limit, "after": params.after or None, "query": params.query or None,
        })
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    conn_data = data.get("orders", {})
    items = [_order_to_entity(e["node"]) for e in (conn_data.get("edges") or [])]
    page_info = conn_data.get("pageInfo", {})
    return ActionResult.ok(OrderList(
        items=items, has_next_page=page_info.get("hasNextPage", False),
        end_cursor=page_info.get("endCursor", "") or "",
    ), summary=f"{len(items)} order(s).")


@chat.function(
    "get_order",
    "Read one order in full: financial/fulfillment status, totals, and every line item.",
    action_type="read",
    chain_callable=True,
    data_model=Order,
    event="shopify-connector.get_order",
)
async def get_order(ctx, params: GetOrderParams) -> ActionResult:
    """Read one order."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = f"query($id: ID!) {{ order(id: $id) {{ {_ORDER_FIELDS} }} }}"
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {"id": params.order_id})
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    order = data.get("order")
    if not order:
        return ActionResult.error("Order not found.", code="not_found")
    return ActionResult.ok(_order_to_entity(order), summary=f"Order '{order.get('name', '')}' loaded.")


@chat.function(
    "cancel_order",
    "Cancel an order, optionally notifying the customer and/or refunding it.",
    action_type="destructive",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.cancel_order",
    effects=["shopify.order.cancelled"],
)
async def cancel_order(ctx, params: CancelOrderParams) -> ActionResult:
    """Cancel an order."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($orderId: ID!, $reason: OrderCancelReason!, $notifyCustomer: Boolean!, $refund: Boolean!, $restock: Boolean!) {
      orderCancel(orderId: $orderId, reason: $reason, notifyCustomer: $notifyCustomer, refund: $refund, restock: $restock) {
        job { id }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "orderId": params.order_id, "reason": params.reason,
            "notifyCustomer": params.notify_customer, "refund": params.refund, "restock": False,
        })
        sc.raise_for_user_errors(data, "orderCancel")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary="Order cancellation queued.")


@chat.function(
    "update_order_note",
    "Set or replace an order's internal note (not visible to the customer).",
    action_type="write",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.update_order_note",
    effects=["shopify.order.updated"],
)
async def update_order_note(ctx, params: UpdateOrderNoteParams) -> ActionResult:
    """Set an order's internal note."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    input_obj = {"id": params.order_id, "note": params.note}
    mutation = """
    mutation($input: OrderInput!) {
      orderUpdate(input: $input) {
        order { id }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "orderUpdate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary="Order note updated.")


@chat.function(
    "create_draft_order",
    "Create a draft order -- a proposed order not yet charged, for phone/custom sales or quotes.",
    action_type="write",
    chain_callable=True,
    data_model=Order,
    event="shopify-connector.create_draft_order",
    effects=["shopify.draft_order.created"],
)
async def create_draft_order(ctx, params: CreateDraftOrderParams) -> ActionResult:
    """Create a draft order."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    try:
        raw_items = json.loads(params.line_items_json)
    except Exception:
        return ActionResult.error("line_items_json must be valid JSON.", code="bad_request")
    line_items = []
    for it in raw_items:
        if it.get("variant_id"):
            line_items.append({"variantId": it["variant_id"], "quantity": it.get("quantity", 1)})
        else:
            line_items.append({
                "title": it.get("title", "Custom item"),
                "quantity": it.get("quantity", 1),
                "originalUnitPrice": it.get("price", "0.00"),
            })
    input_obj: dict = {"lineItems": line_items}
    if params.customer_id:
        input_obj["purchasingEntity"] = {"customerId": params.customer_id}
    if params.email:
        input_obj["email"] = params.email
    if params.note:
        input_obj["note2"] = params.note
    mutation = """
    mutation($input: DraftOrderInput!) {
      draftOrderCreate(input: $input) {
        draftOrder { id name email totalPriceSet { shopMoney { amount currencyCode } } }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "draftOrderCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    d = data["draftOrderCreate"]["draftOrder"]
    return ActionResult.ok(Order(
        id=d.get("id", ""), name=d.get("name", ""), email=d.get("email", "") or "",
        total_price=str((d.get("totalPriceSet", {}).get("shopMoney", {}) or {}).get("amount", "")),
        currency=(d.get("totalPriceSet", {}).get("shopMoney", {}) or {}).get("currencyCode", ""),
    ), summary=f"Draft order '{d.get('name', '')}' created.")


@chat.function(
    "complete_draft_order",
    "Convert a draft order into a real, invoiced order.",
    action_type="write",
    chain_callable=True,
    data_model=Order,
    event="shopify-connector.complete_draft_order",
    effects=["shopify.order.created"],
)
async def complete_draft_order(ctx, params: CompleteDraftOrderParams) -> ActionResult:
    """Complete a draft order."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($id: ID!) {
      draftOrderComplete(id: $id) {
        draftOrder { order { id name displayFinancialStatus } }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"id": params.draft_order_id})
        sc.raise_for_user_errors(data, "draftOrderComplete")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    order = (data["draftOrderComplete"]["draftOrder"] or {}).get("order") or {}
    return ActionResult.ok(Order(
        id=order.get("id", ""), name=order.get("name", ""),
        financial_status=order.get("displayFinancialStatus", "") or "",
    ), summary=f"Draft order completed as '{order.get('name', '')}'.")


@chat.function(
    "cancel_order",
    "Cancel an order, optionally notifying the customer and/or refunding it.",
    action_type="destructive",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.cancel_order",
    effects=["shopify.order.cancelled"],
)
async def cancel_order(ctx, params: CancelOrderParams) -> ActionResult:
    """Cancel an order."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($orderId: ID!, $reason: OrderCancelReason!, $notifyCustomer: Boolean, $refund: Boolean, $restock: Boolean) {
      orderCancel(orderId: $orderId, reason: $reason, notifyCustomer: $notifyCustomer, refund: $refund, restock: $restock) {
        job { id done }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "orderId": params.order_id, "reason": params.reason,
            "notifyCustomer": params.notify_customer, "refund": params.refund, "restock": True,
        })
        sc.raise_for_user_errors(data, "orderCancel")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary="Order cancellation started (async job).")


@chat.function(
    "update_order_note",
    "Set the internal note on an order (not visible to the customer).",
    action_type="write",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.update_order_note",
    effects=["shopify.order.updated"],
)
async def update_order_note(ctx, params: UpdateOrderNoteParams) -> ActionResult:
    """Set an order's internal note."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($input: OrderInput!) {
      orderUpdate(input: $input) { order { id } userErrors { field message } }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "input": {"id": params.order_id, "note": params.note},
        })
        sc.raise_for_user_errors(data, "orderUpdate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary="Order note updated.")


@chat.function(
    "refund_order",
    "Refund an order (full or partial amount), after explicit confirmation.",
    action_type="destructive",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.refund_order",
    effects=["shopify.order.refunded"],
)
async def refund_order(ctx, params: RefundOrderParams) -> ActionResult:
    """Refund an order."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    input_obj: dict = {"orderId": params.order_id, "notify": params.notify_customer}
    if params.note:
        input_obj["note"] = params.note
    if params.amount:
        input_obj["transactions"] = [{
            "orderId": params.order_id, "kind": "REFUND", "gateway": "manual",
            "amount": params.amount,
        }]
    mutation = """
    mutation($input: RefundInput!) {
      refundCreate(input: $input) { refund { id } userErrors { field message } }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "refundCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    refund = data["refundCreate"].get("refund") or {}
    return ActionResult.ok(summary=f"Refund created ({refund.get('id', '')}).")


@chat.function(
    "list_fulfillment_orders",
    "List fulfillment orders for an order -- what still needs to be shipped, and from where.",
    action_type="read",
    chain_callable=True,
    data_model=FulfillmentOrderList,
    event="shopify-connector.list_fulfillment_orders",
)
async def list_fulfillment_orders(ctx, params: ListFulfillmentOrdersParams) -> ActionResult:
    """List fulfillment orders for an order."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query($id: ID!) {
      order(id: $id) {
        fulfillmentOrders(first: 25) {
          edges { node { id status } }
        }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {"id": params.order_id})
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    order = data.get("order") or {}
    items = [
        FulfillmentOrderRef(id=e["node"]["id"], status=e["node"]["status"], order_id=params.order_id)
        for e in (order.get("fulfillmentOrders", {}).get("edges") or [])
    ]
    return ActionResult.ok(FulfillmentOrderList(items=items), summary=f"{len(items)} fulfillment order(s).")


@chat.function(
    "create_fulfillment",
    "Fulfill (ship) a fulfillment order, optionally with tracking info, and notify the customer.",
    action_type="write",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.create_fulfillment",
    effects=["shopify.fulfillment.created"],
)
async def create_fulfillment(ctx, params: CreateFulfillmentParams) -> ActionResult:
    """Create a fulfillment (mark a fulfillment order as shipped)."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    fulfillment_input: dict = {
        "lineItemsByFulfillmentOrder": [{"fulfillmentOrderId": params.fulfillment_order_id}],
        "notifyCustomer": params.notify_customer,
    }
    tracking_info = {}
    if params.tracking_number:
        tracking_info["number"] = params.tracking_number
    if params.tracking_company:
        tracking_info["company"] = params.tracking_company
    if params.tracking_url:
        tracking_info["url"] = params.tracking_url
    if tracking_info:
        fulfillment_input["trackingInfo"] = tracking_info
    mutation = """
    mutation($fulfillment: FulfillmentInput!) {
      fulfillmentCreate(fulfillment: $fulfillment) {
        fulfillment { id status }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"fulfillment": fulfillment_input})
        sc.raise_for_user_errors(data, "fulfillmentCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    f = data["fulfillmentCreate"].get("fulfillment") or {}
    return ActionResult.ok(summary=f"Fulfillment created (status: {f.get('status', '')}).")


@chat.function(
    "cancel_fulfillment",
    "Cancel a fulfillment that hasn't shipped yet.",
    action_type="destructive",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.cancel_fulfillment",
    effects=["shopify.fulfillment.cancelled"],
)
async def cancel_fulfillment(ctx, params: CancelFulfillmentParams) -> ActionResult:
    """Cancel a fulfillment."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($id: ID!) {
      fulfillmentCancel(id: $id) { fulfillment { id status } userErrors { field message } }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"id": params.fulfillment_id})
        sc.raise_for_user_errors(data, "fulfillmentCancel")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary="Fulfillment cancelled.")


# ──────────────────────────────────────────────────────────────────────────
# Customers
# ──────────────────────────────────────────────────────────────────────────


def _customer_to_entity(c: dict) -> Customer:
    return Customer(
        id=c.get("id", ""), first_name=c.get("firstName", "") or "",
        last_name=c.get("lastName", "") or "", email=c.get("email", "") or "",
        phone=c.get("phone", "") or "", orders_count=int(c.get("numberOfOrders", 0) or 0),
        total_spent=str((c.get("amountSpent", {}) or {}).get("amount", "")),
        tags=c.get("tags") or [],
    )


_CUSTOMER_FIELDS = """
  id firstName lastName email phone numberOfOrders tags
  amountSpent { amount currencyCode }
"""


@chat.function(
    "list_customers",
    "List customers in the connected store, with order count and lifetime spend. Supports Shopify search syntax and pagination.",
    action_type="read",
    chain_callable=True,
    data_model=CustomerList,
    event="shopify-connector.list_customers",
)
async def list_customers(ctx, params: ListCustomersParams) -> ActionResult:
    """List customers."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = f"""
    query($first: Int!, $after: String, $query: String) {{
      customers(first: $first, after: $after, query: $query) {{
        pageInfo {{ hasNextPage endCursor }}
        edges {{ node {{ {_CUSTOMER_FIELDS} }} }}
      }}
    }}
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {
            "first": params.limit, "after": params.after or None, "query": params.query or None,
        })
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    conn_data = data.get("customers", {})
    items = [_customer_to_entity(e["node"]) for e in (conn_data.get("edges") or [])]
    page_info = conn_data.get("pageInfo", {})
    return ActionResult.ok(CustomerList(
        items=items, has_next_page=page_info.get("hasNextPage", False),
        end_cursor=page_info.get("endCursor", "") or "",
    ), summary=f"{len(items)} customer(s).")


@chat.function(
    "get_customer",
    "Read one customer's full profile.",
    action_type="read",
    chain_callable=True,
    data_model=Customer,
    event="shopify-connector.get_customer",
)
async def get_customer(ctx, params: GetCustomerParams) -> ActionResult:
    """Read one customer."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = f"query($id: ID!) {{ customer(id: $id) {{ {_CUSTOMER_FIELDS} }} }}"
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {"id": params.customer_id})
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data.get("customer")
    if not node:
        return ActionResult.error(f"No customer with id '{params.customer_id}'.", code="not_found")
    return ActionResult.ok(_customer_to_entity(node))


@chat.function(
    "create_customer",
    "Create a new customer record.",
    action_type="write",
    chain_callable=True,
    data_model=Customer,
    event="shopify-connector.create_customer",
    effects=["shopify.customer.created"],
)
async def create_customer(ctx, params: CreateCustomerParams) -> ActionResult:
    """Create a customer."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    input_obj: dict = {}
    if params.first_name:
        input_obj["firstName"] = params.first_name
    if params.last_name:
        input_obj["lastName"] = params.last_name
    if params.email:
        input_obj["email"] = params.email
    if params.phone:
        input_obj["phone"] = params.phone
    if params.tags:
        input_obj["tags"] = params.tags
    mutation = f"""
    mutation($input: CustomerInput!) {{
      customerCreate(input: $input) {{
        customer {{ {_CUSTOMER_FIELDS} }}
        userErrors {{ field message }}
      }}
    }}
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "customerCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data["customerCreate"]["customer"]
    return ActionResult.ok(_customer_to_entity(node), summary=f"Customer '{node.get('email', '')}' created.")


@chat.function(
    "update_customer",
    "Update selected fields of an existing customer without changing omitted fields.",
    action_type="write",
    chain_callable=True,
    data_model=Customer,
    event="shopify-connector.update_customer",
    effects=["shopify.customer.updated"],
)
async def update_customer(ctx, params: UpdateCustomerParams) -> ActionResult:
    """Update a customer."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    input_obj: dict = {"id": params.customer_id}
    if params.first_name:
        input_obj["firstName"] = params.first_name
    if params.last_name:
        input_obj["lastName"] = params.last_name
    if params.email:
        input_obj["email"] = params.email
    if params.phone:
        input_obj["phone"] = params.phone
    if params.tags:
        input_obj["tags"] = params.tags
    mutation = f"""
    mutation($input: CustomerInput!) {{
      customerUpdate(input: $input) {{
        customer {{ {_CUSTOMER_FIELDS} }}
        userErrors {{ field message }}
      }}
    }}
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "customerUpdate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data["customerUpdate"]["customer"]
    return ActionResult.ok(_customer_to_entity(node), summary="Customer updated.")


@chat.function(
    "delete_customer",
    "Permanently delete a customer. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="shopify-connector.delete_customer",
    effects=["shopify.customer.deleted"],
)
async def delete_customer(ctx, params: DeleteCustomerParams) -> ActionResult:
    """Delete a customer."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($input: CustomerDeleteInput!) {
      customerDelete(input: $input) { deletedCustomerId userErrors { field message } }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": {"id": params.customer_id}})
        sc.raise_for_user_errors(data, "customerDelete")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    deleted_id = data["customerDelete"].get("deletedCustomerId", params.customer_id)
    return ActionResult.ok(DeleteResult(deleted=True, id=deleted_id), summary="Customer deleted.")


# ──────────────────────────────────────────────────────────────────────────
# Inventory / Locations
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_locations",
    "List the store's fulfillment locations (warehouses/stores).",
    action_type="read",
    chain_callable=True,
    data_model=LocationList,
    event="shopify-connector.list_locations",
)
async def list_locations(ctx, params: ListLocationsParams) -> ActionResult:
    """List locations."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query {
      locations(first: 50) {
        edges { node { id name isActive fulfillsOnlineOrders } }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query)
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    items = [
        Location(
            id=e["node"]["id"], name=e["node"]["name"],
            is_active=e["node"].get("isActive", False),
            fulfills_online_orders=e["node"].get("fulfillsOnlineOrders", False),
        )
        for e in (data.get("locations", {}).get("edges") or [])
    ]
    return ActionResult.ok(LocationList(items=items), summary=f"{len(items)} location(s).")


@chat.function(
    "get_inventory_levels",
    "Read an inventory item's available quantity at every location.",
    action_type="read",
    chain_callable=True,
    data_model=InventoryLevelList,
    event="shopify-connector.get_inventory_levels",
)
async def get_inventory_levels(ctx, params: GetInventoryLevelsParams) -> ActionResult:
    """Read inventory levels for one item."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query($id: ID!) {
      inventoryItem(id: $id) {
        inventoryLevels(first: 50) {
          edges { node { location { id } quantities(names: ["available"]) { quantity } } }
        }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {"id": params.inventory_item_id})
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    item = data.get("inventoryItem") or {}
    items = []
    for e in (item.get("inventoryLevels", {}).get("edges") or []):
        node = e["node"]
        qty = (node.get("quantities") or [{}])[0].get("quantity", 0)
        items.append(InventoryLevel(
            inventory_item_id=params.inventory_item_id,
            location_id=(node.get("location") or {}).get("id", ""),
            available=qty,
        ))
    return ActionResult.ok(InventoryLevelList(items=items), summary=f"{len(items)} location level(s).")


@chat.function(
    "set_inventory_quantity",
    "Set the absolute on-hand quantity for an inventory item at one location.",
    action_type="write",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.set_inventory_quantity",
    effects=["shopify.inventory.updated"],
)
async def set_inventory_quantity(ctx, params: SetInventoryQuantityParams) -> ActionResult:
    """Set absolute inventory quantity."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($input: InventorySetQuantitiesInput!) {
      inventorySetQuantities(input: $input) {
        inventoryAdjustmentGroup { createdAt }
        userErrors { field message }
      }
    }
    """
    input_obj = {
        "name": "available",
        "reason": "correction",
        "ignoreCompareQuantity": True,
        "quantities": [{
            "inventoryItemId": params.inventory_item_id,
            "locationId": params.location_id,
            "quantity": params.quantity,
        }],
    }
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "inventorySetQuantities")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary=f"Inventory set to {params.quantity}.")


@chat.function(
    "adjust_inventory_quantity",
    "Adjust an inventory item's quantity at one location by a relative delta (e.g. -3 or +10).",
    action_type="write",
    chain_callable=True,
    data_model=NoParams,
    event="shopify-connector.adjust_inventory_quantity",
    effects=["shopify.inventory.updated"],
)
async def adjust_inventory_quantity(ctx, params: AdjustInventoryQuantityParams) -> ActionResult:
    """Adjust inventory by a relative delta."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($input: InventoryAdjustQuantitiesInput!) {
      inventoryAdjustQuantities(input: $input) {
        inventoryAdjustmentGroup { createdAt }
        userErrors { field message }
      }
    }
    """
    input_obj = {
        "name": "available",
        "reason": "correction",
        "changes": [{
            "inventoryItemId": params.inventory_item_id,
            "locationId": params.location_id,
            "delta": params.delta,
        }],
    }
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"input": input_obj})
        sc.raise_for_user_errors(data, "inventoryAdjustQuantities")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(summary=f"Inventory adjusted by {params.delta:+d}.")


# ──────────────────────────────────────────────────────────────────────────
# Discounts
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_discounts",
    "List discount codes and automatic discounts configured on the store.",
    action_type="read",
    chain_callable=True,
    data_model=DiscountList,
    event="shopify-connector.list_discounts",
)
async def list_discounts(ctx, params: ListDiscountsParams) -> ActionResult:
    """List discounts."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query($first: Int!) {
      discountNodes(first: $first) {
        edges {
          node {
            id
            discount {
              __typename
              ... on DiscountCodeBasic { title status codes(first: 1) { edges { node { code } } } }
              ... on DiscountAutomaticBasic { title status }
            }
          }
        }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {"first": params.limit})
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    items = []
    for e in (data.get("discountNodes", {}).get("edges") or []):
        n = e["node"]
        d = n.get("discount") or {}
        codes = d.get("codes", {}).get("edges") or []
        items.append(Discount(
            id=n["id"], title=d.get("title", "") or "", status=d.get("status", "") or "",
            kind=d.get("__typename", ""),
            code=(codes[0]["node"]["code"] if codes else ""),
        ))
    return ActionResult.ok(DiscountList(items=items), summary=f"{len(items)} discount(s).")


@chat.function(
    "create_code_discount",
    "Create a discount code (percentage or fixed-amount off), optionally limited to specific products/collections and with usage/date limits.",
    action_type="write",
    chain_callable=True,
    data_model=Discount,
    event="shopify-connector.create_code_discount",
    effects=["shopify.discount.created"],
)
async def create_code_discount(ctx, params: CreateCodeDiscountParams) -> ActionResult:
    """Create a discount code."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    value: dict
    if params.percentage is not None:
        value = {"percentage": params.percentage / 100.0}
    else:
        value = {"discountAmount": {"amount": str(params.amount), "appliesOnEachItem": False}}
    basic_input: dict = {
        "title": params.title,
        "code": params.code,
        "startsAt": params.starts_at,
        "customerSelection": {"all": True},
        "customerGets": {
            "value": value,
            "items": {"all": True},
        },
    }
    if params.ends_at:
        basic_input["endsAt"] = params.ends_at
    if params.usage_limit:
        basic_input["usageLimit"] = params.usage_limit
    mutation = """
    mutation($basicCodeDiscount: DiscountCodeBasicInput!) {
      discountCodeBasicCreate(basicCodeDiscount: $basicCodeDiscount) {
        codeDiscountNode { id codeDiscount { ... on DiscountCodeBasic { title status codes(first: 1) { edges { node { code } } } } } }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"basicCodeDiscount": basic_input})
        sc.raise_for_user_errors(data, "discountCodeBasicCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data["discountCodeBasicCreate"].get("codeDiscountNode") or {}
    d = (node.get("codeDiscount") or {})
    codes = d.get("codes", {}).get("edges") or []
    return ActionResult.ok(Discount(
        id=node.get("id", ""), title=d.get("title", "") or "", status=d.get("status", "") or "",
        kind="DiscountCodeBasic", code=(codes[0]["node"]["code"] if codes else params.code),
    ), summary=f"Discount code '{params.code}' created.")


@chat.function(
    "create_automatic_discount",
    "Create an automatic discount (applies at checkout with no code), percentage or fixed-amount off.",
    action_type="write",
    chain_callable=True,
    data_model=Discount,
    event="shopify-connector.create_automatic_discount",
    effects=["shopify.discount.created"],
)
async def create_automatic_discount(ctx, params: CreateAutomaticDiscountParams) -> ActionResult:
    """Create an automatic discount."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    value: dict
    if params.percentage is not None:
        value = {"percentage": params.percentage / 100.0}
    else:
        value = {"discountAmount": {"amount": str(params.amount), "appliesOnEachItem": False}}
    basic_input: dict = {
        "title": params.title,
        "startsAt": params.starts_at,
        "customerGets": {"value": value, "items": {"all": True}},
    }
    if params.ends_at:
        basic_input["endsAt"] = params.ends_at
    mutation = """
    mutation($automaticBasicDiscount: DiscountAutomaticBasicInput!) {
      discountAutomaticBasicCreate(automaticBasicDiscount: $automaticBasicDiscount) {
        automaticDiscountNode { id automaticDiscount { ... on DiscountAutomaticBasic { title status } } }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"automaticBasicDiscount": basic_input})
        sc.raise_for_user_errors(data, "discountAutomaticBasicCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data["discountAutomaticBasicCreate"].get("automaticDiscountNode") or {}
    d = (node.get("automaticDiscount") or {})
    return ActionResult.ok(Discount(
        id=node.get("id", ""), title=d.get("title", "") or "", status=d.get("status", "") or "",
        kind="DiscountAutomaticBasic", code="",
    ), summary=f"Automatic discount '{params.title}' created.")


@chat.function(
    "delete_discount",
    "Permanently delete a discount (code or automatic) by id.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="shopify-connector.delete_discount",
    effects=["shopify.discount.deleted"],
)
async def delete_discount(ctx, params: DeleteDiscountParams) -> ActionResult:
    """Delete a discount."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($id: ID!) {
      discountCodeDelete(id: $id) { deletedCodeDiscountId userErrors { field message } }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"id": params.discount_id})
        sc.raise_for_user_errors(data, "discountCodeDelete")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(DeleteResult(deleted=True, id=params.discount_id), summary="Discount deleted.")


# ──────────────────────────────────────────────────────────────────────────
# Metafields
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_metafields",
    "List custom metafields stored on a product, customer, or order (owner resource).",
    action_type="read",
    chain_callable=True,
    data_model=MetafieldList,
    event="shopify-connector.list_metafields",
)
async def list_metafields(ctx, params: ListMetafieldsParams) -> ActionResult:
    """List metafields on a resource."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query($id: ID!) {
      node(id: $id) {
        ... on HasMetafields {
          metafields(first: 50) {
            edges { node { id namespace key value type } }
          }
        }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query, {"id": params.owner_id})
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    node = data.get("node") or {}
    items = [
        Metafield(id=e["node"]["id"], namespace=e["node"]["namespace"], key=e["node"]["key"],
                  value=e["node"]["value"], type=e["node"]["type"])
        for e in (node.get("metafields", {}).get("edges") or [])
    ]
    return ActionResult.ok(MetafieldList(items=items), summary=f"{len(items)} metafield(s).")


@chat.function(
    "set_metafield",
    "Create or update a custom metafield on a product, customer, or order -- store any extra structured data Shopify doesn't have a native field for.",
    action_type="write",
    chain_callable=True,
    data_model=Metafield,
    event="shopify-connector.set_metafield",
    effects=["shopify.metafield.set"],
)
async def set_metafield(ctx, params: SetMetafieldParams) -> ActionResult:
    """Set (create or update) a metafield."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        metafields { id namespace key value type }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "metafields": [{
                "ownerId": params.owner_id, "namespace": params.namespace,
                "key": params.key, "value": params.value, "type": params.type,
            }],
        })
        sc.raise_for_user_errors(data, "metafieldsSet")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    mfs = data["metafieldsSet"].get("metafields") or []
    if not mfs:
        return ActionResult.error("Shopify did not return the set metafield.", code="empty_response")
    m = mfs[0]
    return ActionResult.ok(Metafield(id=m["id"], namespace=m["namespace"], key=m["key"], value=m["value"], type=m["type"]),
                            summary=f"Metafield '{m['namespace']}.{m['key']}' set.")


@chat.function(
    "delete_metafield",
    "Permanently delete a metafield by id.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="shopify-connector.delete_metafield",
    effects=["shopify.metafield.deleted"],
)
async def delete_metafield(ctx, params: DeleteMetafieldParams) -> ActionResult:
    """Delete a metafield."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($id: ID!) {
      metafieldDelete(input: { id: $id }) { deletedId userErrors { field message } }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"id": params.metafield_id})
        sc.raise_for_user_errors(data, "metafieldDelete")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(DeleteResult(deleted=True, id=params.metafield_id), summary="Metafield deleted.")


# ──────────────────────────────────────────────────────────────────────────
# Webhooks
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_webhooks",
    "List webhook subscriptions configured on the store -- which topics notify which URL.",
    action_type="read",
    chain_callable=True,
    data_model=WebhookList,
    event="shopify-connector.list_webhooks",
)
async def list_webhooks(ctx, params: ListWebhooksParams) -> ActionResult:
    """List webhook subscriptions."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query {
      webhookSubscriptions(first: 50) {
        edges {
          node {
            id topic createdAt
            endpoint { __typename ... on WebhookHttpEndpoint { callbackUrl } }
          }
        }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query)
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    items = []
    for e in (data.get("webhookSubscriptions", {}).get("edges") or []):
        n = e["node"]
        ep = n.get("endpoint") or {}
        items.append(WebhookSubscription(id=n["id"], topic=n["topic"], callback_url=ep.get("callbackUrl", "") or ""))
    return ActionResult.ok(WebhookList(items=items), summary=f"{len(items)} webhook subscription(s).")


@chat.function(
    "create_webhook",
    "Subscribe to a Shopify event topic (e.g. ORDERS_CREATE, PRODUCTS_UPDATE) -- Shopify will POST a notification to the given HTTPS URL whenever it happens.",
    action_type="write",
    chain_callable=True,
    data_model=WebhookSubscription,
    event="shopify-connector.create_webhook",
    effects=["shopify.webhook.created"],
)
async def create_webhook(ctx, params: CreateWebhookParams) -> ActionResult:
    """Create a webhook subscription."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($topic: WebhookSubscriptionTopic!, $webhookSubscription: WebhookSubscriptionInput!) {
      webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
        webhookSubscription { id topic endpoint { __typename ... on WebhookHttpEndpoint { callbackUrl } } }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {
            "topic": params.topic, "webhookSubscription": {"callbackUrl": params.callback_url},
        })
        sc.raise_for_user_errors(data, "webhookSubscriptionCreate")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    n = data["webhookSubscriptionCreate"].get("webhookSubscription") or {}
    ep = n.get("endpoint") or {}
    return ActionResult.ok(
        WebhookSubscription(id=n.get("id", ""), topic=n.get("topic", ""), callback_url=ep.get("callbackUrl", "") or ""),
        summary=f"Webhook subscribed to '{n.get('topic', '')}'.",
    )


@chat.function(
    "delete_webhook",
    "Permanently remove a webhook subscription by id.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="shopify-connector.delete_webhook",
    effects=["shopify.webhook.deleted"],
)
async def delete_webhook(ctx, params: DeleteWebhookParams) -> ActionResult:
    """Delete a webhook subscription."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($id: ID!) {
      webhookSubscriptionDelete(id: $id) { deletedWebhookSubscriptionId userErrors { field message } }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"id": params.webhook_id})
        sc.raise_for_user_errors(data, "webhookSubscriptionDelete")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(DeleteResult(deleted=True, id=params.webhook_id), summary="Webhook subscription deleted.")


# ──────────────────────────────────────────────────────────────────────────
# Bulk Operations (Tier 2 -- large-catalog export)
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "run_bulk_query",
    "Start a bulk export of a large dataset (e.g. every product or every order) via Shopify's asynchronous Bulk Operations API -- use for exports too large for a normal paginated query.",
    action_type="write",
    chain_callable=True,
    data_model=BulkOperationStatus,
    event="shopify-connector.run_bulk_query",
    effects=["create:resource"],
)
async def run_bulk_query(ctx, params: RunBulkQueryParams) -> ActionResult:
    """Start a bulk query operation."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($query: String!) {
      bulkOperationRunQuery(query: $query) {
        bulkOperation { id status }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"query": params.bulk_query})
        sc.raise_for_user_errors(data, "bulkOperationRunQuery")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    op = data["bulkOperationRunQuery"].get("bulkOperation") or {}
    return ActionResult.ok(BulkOperationStatus(id=op.get("id", ""), status=op.get("status", "")),
                            summary="Bulk query started -- check status with get_bulk_operation_status.")


@chat.function(
    "get_bulk_operation_status",
    "Check the status of the current (or a specific) bulk operation, and get the download URL once it completes.",
    action_type="read",
    chain_callable=True,
    data_model=BulkOperationStatus,
    event="shopify-connector.get_bulk_operation_status",
)
async def get_bulk_operation_status(ctx, params: GetBulkOperationStatusParams) -> ActionResult:
    """Read bulk operation status."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query {
      currentBulkOperation {
        id status errorCode objectCount url partialDataUrl
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query)
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    op = data.get("currentBulkOperation") or {}
    return ActionResult.ok(BulkOperationStatus(
        id=op.get("id", ""), status=op.get("status", ""), error_code=op.get("errorCode", "") or "",
        object_count=int(op.get("objectCount", 0) or 0), url=op.get("url", "") or "",
    ), summary=f"Bulk operation status: {op.get('status', 'UNKNOWN')}.")


@chat.function(
    "cancel_bulk_operation",
    "Cancel a currently running bulk operation.",
    action_type="write",
    chain_callable=True,
    data_model=BulkOperationStatus,
    event="shopify-connector.cancel_bulk_operation",
    effects=["shopify.bulk_operation.cancelled"],
)
async def cancel_bulk_operation(ctx, params: CancelBulkOperationParams) -> ActionResult:
    """Cancel a bulk operation."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    mutation = """
    mutation($id: ID!) {
      bulkOperationCancel(id: $id) {
        bulkOperation { id status }
        userErrors { field message }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], mutation, {"id": params.operation_id})
        sc.raise_for_user_errors(data, "bulkOperationCancel")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    op = data["bulkOperationCancel"].get("bulkOperation") or {}
    return ActionResult.ok(BulkOperationStatus(id=op.get("id", ""), status=op.get("status", "")),
                            summary="Bulk operation cancellation requested.")


# ──────────────────────────────────────────────────────────────────────────
# Value-add reports (Tier 3) -- these do not exist as single Shopify API
# calls; they compose several reads into one useful business answer, same
# pattern as MuleSoft Connector's audit_cloudhub_environment.
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "get_low_stock_report",
    "Value-add report: scan products and flag every variant whose available inventory is at or below a threshold, across all locations. Shopify has no single API call for this -- it composes list_products-style paging with inventory levels.",
    action_type="read",
    chain_callable=True,
    data_model=LowStockReport,
    event="shopify-connector.get_low_stock_report",
)
async def get_low_stock_report(ctx, params: GetLowStockReportParams) -> ActionResult:
    """Build a low-stock report across the catalog."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query($first: Int!, $after: String) {
      products(first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            title
            variants(first: 100) {
              edges {
                node {
                  title sku inventoryQuantity
                  inventoryItem {
                    inventoryLevels(first: 10) {
                      edges { node { location { name } quantities(names: ["available"]) { name quantity } } }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    rows: list[LowStockRow] = []
    after = None
    scanned = 0
    try:
        while scanned < params.limit:
            data = await sc.graphql(ctx, token, conn["shop_domain"], query, {
                "first": min(50, params.limit - scanned), "after": after,
            })
            conn_data = data.get("products", {})
            edges = conn_data.get("edges") or []
            for e in edges:
                p = e["node"]
                for ve in (p.get("variants", {}).get("edges") or []):
                    v = ve["node"]
                    levels = ((v.get("inventoryItem") or {}).get("inventoryLevels", {}).get("edges") or [])
                    if not levels:
                        continue
                    for lv in levels:
                        node = lv["node"]
                        qty_entries = node.get("quantities") or []
                        available = qty_entries[0]["quantity"] if qty_entries else 0
                        if available <= params.threshold:
                            rows.append(LowStockRow(
                                product_title=p.get("title", ""), variant_title=v.get("title", ""),
                                sku=v.get("sku", "") or "", available=available,
                                location=(node.get("location") or {}).get("name", ""),
                            ))
            scanned += len(edges)
            page_info = conn_data.get("pageInfo", {})
            if not page_info.get("hasNextPage") or not edges:
                break
            after = page_info.get("endCursor")
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    return ActionResult.ok(LowStockReport(rows=rows, threshold=params.threshold),
                            summary=f"{len(rows)} variant/location combo(s) at or below {params.threshold} units.")


@chat.function(
    "get_store_summary",
    "Value-add report: one-glance store health snapshot -- total products, orders and revenue in the last 30 days, customer count, and currently open orders. Composes several GraphQL reads into one business answer.",
    action_type="read",
    chain_callable=True,
    data_model=StoreSummary,
    event="shopify-connector.get_store_summary",
)
async def get_store_summary(ctx, params: GetStoreSummaryParams) -> ActionResult:
    """Build a one-glance store summary."""
    conn, token, err = await _resolve_or_error(ctx, params.connection_id)
    if err:
        return err
    query = """
    query {
      products(first: 1) { pageInfo { hasNextPage } }
      productsCount: products(first: 250) { edges { node { id } } pageInfo { hasNextPage } }
      customersCount: customers(first: 250) { edges { node { id } } pageInfo { hasNextPage } }
      recentOrders: orders(first: 250, query: "created_at:>=-30d") {
        edges { node { id displayFinancialStatus totalPriceSet { shopMoney { amount currencyCode } } } }
      }
      openOrders: orders(first: 250, query: "fulfillment_status:unfulfilled") {
        edges { node { id } }
      }
    }
    """
    try:
        data = await sc.graphql(ctx, token, conn["shop_domain"], query)
    except sc.ClientFail as e:
        return ActionResult.error(str(e), code=e.code)
    recent = data.get("recentOrders", {}).get("edges") or []
    revenue = sum(float((e["node"].get("totalPriceSet", {}).get("shopMoney", {}) or {}).get("amount", 0) or 0) for e in recent)
    currency = ""
    if recent:
        currency = (recent[0]["node"].get("totalPriceSet", {}).get("shopMoney", {}) or {}).get("currencyCode", "")
    summary = StoreSummary(
        products_count=len(data.get("productsCount", {}).get("edges") or []),
        orders_count_last_30d=len(recent),
        revenue_last_30d=f"{revenue:.2f} {currency}".strip(),
        customers_count=len(data.get("customersCount", {}).get("edges") or []),
        open_orders_count=len(data.get("openOrders", {}).get("edges") or []),
    )
    return ActionResult.ok(summary, summary=f"{summary.orders_count_last_30d} orders / {summary.revenue_last_30d} in the last 30 days.")
