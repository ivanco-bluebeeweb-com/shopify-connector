"""Pydantic params models + SDL entity contracts for Shopify Connector.

All params models are module-scope (V17 federal invariant, same rule as
MuleSoft Connector / Power Automate Connector / n8n Connector's schemas.py).
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from imperal_sdk import sdl


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


class ConnectShopifyParams(BaseModel):
    shop_domain: str = Field(
        "",
        description="Your Shopify store's *.myshopify.com domain, e.g. 'my-store.myshopify.com'.",
    )
    access_token: str = Field(
        "",
        description="Admin API access token from a Custom App created in your store's Settings > Apps and sales channels > Develop apps.",
    )
    label: str = Field("", description="Optional friendly name for this store connection.")


class ProviderConnection(sdl.Entity):
    id: str = ""
    title: str = ""
    connected: bool = False
    detail: str = ""
    shop_domain: str = ""


class ProviderConnectionList(sdl.Entity):
    items: list[ProviderConnection] = []


class DisconnectShopifyParams(BaseModel):
    connection_id: str = Field(..., description="Connection id from list_connections.")


class DeleteResult(sdl.Entity):
    deleted: bool = False
    id: str = ""


class ConnParams(BaseModel):
    """Base params carrying an optional connection_id -- omit to use the
    only/default connected store."""
    connection_id: str = Field("", description="Which connected store to use. Omit if only one is connected.")


class ListConnectionsParams(NoParams):
    pass


# ──────────────────────────────────────────────────────────────────────────
# Products / Variants / Media / Collections
# ──────────────────────────────────────────────────────────────────────────


class ProductVariant(sdl.Entity):
    id: str = ""
    title: str = ""
    sku: str = ""
    price: str = ""
    compare_at_price: str = ""
    inventory_quantity: int = 0
    inventory_item_id: str = ""


class Product(sdl.Entity):
    id: str = ""
    title: str = ""
    handle: str = ""
    status: str = ""
    vendor: str = ""
    product_type: str = ""
    tags: list[str] = []
    variants: list[ProductVariant] = []
    featured_image: str = ""
    created_at: str = ""
    updated_at: str = ""


class ProductList(sdl.Entity):
    items: list[Product] = []
    has_next_page: bool = False
    end_cursor: str = ""


class ListProductsParams(ConnParams):
    limit: int = Field(25, ge=1, le=250, description="Max products to return.")
    after: str = Field("", description="Pagination cursor from a previous call's end_cursor.")
    query: str = Field("", description="Shopify search syntax, e.g. \"status:active\" or \"title:*shirt*\".")


class GetProductParams(ConnParams):
    product_id: str = Field(..., description="Product GID, e.g. gid://shopify/Product/123.")


class CreateProductParams(ConnParams):
    title: str = Field(..., description="Product title.")
    description_html: str = Field("", description="Product description as HTML.")
    vendor: str = Field("", description="Vendor/brand name.")
    product_type: str = Field("", description="Product category/type.")
    tags: list[str] = Field(default_factory=list, description="Tags for organization/search.")
    status: str = Field("DRAFT", description="ACTIVE, ARCHIVED, or DRAFT.")


class UpdateProductParams(ConnParams):
    product_id: str = Field(..., description="Product GID to update.")
    title: str = Field("", description="New title, omit to leave unchanged.")
    description_html: str = Field("", description="New description HTML, omit to leave unchanged.")
    vendor: str = Field("", description="New vendor, omit to leave unchanged.")
    product_type: str = Field("", description="New product type, omit to leave unchanged.")
    status: str = Field("", description="ACTIVE, ARCHIVED, or DRAFT; omit to leave unchanged.")
    tags: list[str] = Field(default_factory=list, description="Replace tags; omit (empty) to leave unchanged.")


class DeleteProductParams(ConnParams):
    product_id: str = Field(..., description="Product GID to permanently delete.")


class CreateProductVariantParams(ConnParams):
    product_id: str = Field(..., description="Parent product GID.")
    price: str = Field(..., description="Variant price, e.g. '19.99'.")
    sku: str = Field("", description="Variant SKU.")
    compare_at_price: str = Field("", description="Compare-at (was) price.")
    option_values: list[str] = Field(default_factory=list, description="Option values, e.g. ['Red', 'Large'].")


class UpdateProductVariantParams(ConnParams):
    variant_id: str = Field(..., description="ProductVariant GID to update.")
    price: str = Field("", description="New price, omit to leave unchanged.")
    sku: str = Field("", description="New SKU, omit to leave unchanged.")
    compare_at_price: str = Field("", description="New compare-at price, omit to leave unchanged.")


class DeleteProductVariantParams(ConnParams):
    product_id: str = Field(..., description="Parent product GID.")
    variant_id: str = Field(..., description="ProductVariant GID to delete.")


class UploadProductMediaParams(ConnParams):
    product_id: str = Field(..., description="Product GID to attach media to.")
    image_url: str = Field(..., description="Publicly reachable https:// image URL.")
    alt_text: str = Field("", description="Alt text for accessibility/SEO.")


class Collection(sdl.Entity):
    id: str = ""
    title: str = ""
    handle: str = ""
    products_count: int = 0
    is_smart: bool = False


class CollectionList(sdl.Entity):
    items: list[Collection] = []
    has_next_page: bool = False
    end_cursor: str = ""


class ListCollectionsParams(ConnParams):
    limit: int = Field(25, ge=1, le=250)
    after: str = Field("", description="Pagination cursor.")


class CreateCollectionParams(ConnParams):
    title: str = Field(..., description="Collection title.")
    description_html: str = Field("", description="Collection description as HTML.")
    rules_json: str = Field("", description="Optional JSON array of smart-collection rules; omit for a manual collection.")


class AddProductsToCollectionParams(ConnParams):
    collection_id: str = Field(..., description="Collection GID.")
    product_ids: list[str] = Field(..., description="Product GIDs to add.")


class RemoveProductsFromCollectionParams(ConnParams):
    collection_id: str = Field(..., description="Collection GID.")
    product_ids: list[str] = Field(..., description="Product GIDs to remove.")


# ──────────────────────────────────────────────────────────────────────────
# Orders / Draft Orders / Refunds / Fulfillment
# ──────────────────────────────────────────────────────────────────────────


class OrderLineItem(sdl.Entity):
    id: str = ""
    title: str = ""
    quantity: int = 0
    sku: str = ""
    price: str = ""


class Order(sdl.Entity):
    id: str = ""
    name: str = ""
    email: str = ""
    financial_status: str = ""
    fulfillment_status: str = ""
    total_price: str = ""
    currency: str = ""
    created_at: str = ""
    line_items: list[OrderLineItem] = []
    customer_id: str = ""


class OrderList(sdl.Entity):
    items: list[Order] = []
    has_next_page: bool = False
    end_cursor: str = ""


class ListOrdersParams(ConnParams):
    limit: int = Field(25, ge=1, le=250)
    after: str = Field("", description="Pagination cursor.")
    query: str = Field("", description="Shopify search syntax, e.g. \"financial_status:paid\".")


class GetOrderParams(ConnParams):
    order_id: str = Field(..., description="Order GID.")


class CancelOrderParams(ConnParams):
    order_id: str = Field(..., description="Order GID to cancel.")
    reason: str = Field("CUSTOMER", description="CUSTOMER, DECLINED, FRAUD, INVENTORY, STAFF, or OTHER.")
    notify_customer: bool = Field(False, description="Whether to email the customer about the cancellation.")
    refund: bool = Field(False, description="Whether to also refund the order.")


class UpdateOrderNoteParams(ConnParams):
    order_id: str = Field(..., description="Order GID.")
    note: str = Field(..., description="Internal note text (not visible to the customer).")


class DraftOrderLineItemInput(BaseModel):
    variant_id: str = Field("", description="ProductVariant GID; omit for a custom line item.")
    title: str = Field("", description="Custom line item title (when no variant_id).")
    quantity: int = Field(1, ge=1)
    price: str = Field("", description="Custom line item price (when no variant_id).")


class CreateDraftOrderParams(ConnParams):
    line_items_json: str = Field(..., description="JSON array of line items: [{variant_id|title/price, quantity}, ...].")
    customer_id: str = Field("", description="Customer GID to attach, optional.")
    email: str = Field("", description="Customer email if no customer_id.")
    note: str = Field("", description="Order note.")


class CompleteDraftOrderParams(ConnParams):
    draft_order_id: str = Field(..., description="DraftOrder GID to convert into a real order.")


class RefundOrderParams(ConnParams):
    order_id: str = Field(..., description="Order GID to refund.")
    amount: str = Field("", description="Amount to refund; omit to refund line items' full value.")
    notify_customer: bool = Field(True, description="Whether to email the customer about the refund.")
    note: str = Field("", description="Internal note about the refund reason.")


class FulfillmentOrderRef(sdl.Entity):
    id: str = ""
    status: str = ""
    order_id: str = ""


class ListFulfillmentOrdersParams(ConnParams):
    order_id: str = Field(..., description="Order GID whose fulfillment orders to list.")


class FulfillmentOrderList(sdl.Entity):
    items: list[FulfillmentOrderRef] = []


class CreateFulfillmentParams(ConnParams):
    fulfillment_order_id: str = Field(..., description="FulfillmentOrder GID to fulfill.")
    tracking_number: str = Field("", description="Shipment tracking number.")
    tracking_company: str = Field("", description="Carrier name, e.g. UPS.")
    tracking_url: str = Field("", description="Tracking URL.")
    notify_customer: bool = Field(True, description="Whether to email the customer their tracking info.")


class CancelFulfillmentParams(ConnParams):
    fulfillment_id: str = Field(..., description="Fulfillment GID to cancel.")


# ──────────────────────────────────────────────────────────────────────────
# Customers
# ──────────────────────────────────────────────────────────────────────────


class Customer(sdl.Entity):
    id: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    orders_count: int = 0
    total_spent: str = ""
    tags: list[str] = []


class CustomerList(sdl.Entity):
    items: list[Customer] = []
    has_next_page: bool = False
    end_cursor: str = ""


class ListCustomersParams(ConnParams):
    limit: int = Field(25, ge=1, le=250)
    after: str = Field("", description="Pagination cursor.")
    query: str = Field("", description="Shopify search syntax, e.g. \"email:*@acme.com\".")


class GetCustomerParams(ConnParams):
    customer_id: str = Field(..., description="Customer GID.")


class CreateCustomerParams(ConnParams):
    first_name: str = Field("", description="First name.")
    last_name: str = Field("", description="Last name.")
    email: str = Field("", description="Email address.")
    phone: str = Field("", description="Phone number, E.164 format preferred.")
    tags: list[str] = Field(default_factory=list, description="Tags for segmentation.")


class UpdateCustomerParams(ConnParams):
    customer_id: str = Field(..., description="Customer GID to update.")
    first_name: str = Field("", description="New first name, omit to leave unchanged.")
    last_name: str = Field("", description="New last name, omit to leave unchanged.")
    email: str = Field("", description="New email, omit to leave unchanged.")
    phone: str = Field("", description="New phone, omit to leave unchanged.")
    tags: list[str] = Field(default_factory=list, description="Replace tags; omit (empty) to leave unchanged.")


class DeleteCustomerParams(ConnParams):
    customer_id: str = Field(..., description="Customer GID to permanently delete.")


# ──────────────────────────────────────────────────────────────────────────
# Inventory / Locations
# ──────────────────────────────────────────────────────────────────────────


class Location(sdl.Entity):
    id: str = ""
    name: str = ""
    is_active: bool = False
    fulfills_online_orders: bool = False


class LocationList(sdl.Entity):
    items: list[Location] = []


class ListLocationsParams(ConnParams):
    pass


class InventoryLevel(sdl.Entity):
    inventory_item_id: str = ""
    location_id: str = ""
    available: int = 0


class GetInventoryLevelsParams(ConnParams):
    inventory_item_id: str = Field(..., description="InventoryItem GID.")


class InventoryLevelList(sdl.Entity):
    items: list[InventoryLevel] = []


class SetInventoryQuantityParams(ConnParams):
    inventory_item_id: str = Field(..., description="InventoryItem GID.")
    location_id: str = Field(..., description="Location GID.")
    quantity: int = Field(..., ge=0, description="Absolute on-hand quantity to set.")


class AdjustInventoryQuantityParams(ConnParams):
    inventory_item_id: str = Field(..., description="InventoryItem GID.")
    location_id: str = Field(..., description="Location GID.")
    delta: int = Field(..., description="Relative change, e.g. -3 or +10.")


# ──────────────────────────────────────────────────────────────────────────
# Discounts
# ──────────────────────────────────────────────────────────────────────────


class Discount(sdl.Entity):
    id: str = ""
    title: str = ""
    code: str = ""
    status: str = ""
    kind: str = ""


class DiscountList(sdl.Entity):
    items: list[Discount] = []


class ListDiscountsParams(ConnParams):
    limit: int = Field(25, ge=1, le=250)


class CreateCodeDiscountParams(ConnParams):
    title: str = Field(..., description="Internal title for the discount.")
    code: str = Field(..., description="The code customers enter at checkout.")
    percentage: float = Field(0.0, ge=0.0, le=1.0, description="Discount as a fraction, e.g. 0.15 for 15% off.")
    starts_at: str = Field("", description="ISO 8601 start datetime; omit for immediately.")
    ends_at: str = Field("", description="ISO 8601 end datetime; omit for no end date.")


class CreateAutomaticDiscountParams(ConnParams):
    title: str = Field(..., description="Internal title (shown at checkout, no code needed).")
    percentage: float = Field(0.0, ge=0.0, le=1.0, description="Discount as a fraction, e.g. 0.10 for 10% off.")
    starts_at: str = Field("", description="ISO 8601 start datetime; omit for immediately.")
    ends_at: str = Field("", description="ISO 8601 end datetime; omit for no end date.")


class DeleteDiscountParams(ConnParams):
    discount_id: str = Field(..., description="DiscountCodeNode or DiscountAutomaticNode GID to delete.")


# ──────────────────────────────────────────────────────────────────────────
# Metafields
# ──────────────────────────────────────────────────────────────────────────


class Metafield(sdl.Entity):
    id: str = ""
    namespace: str = ""
    key: str = ""
    value: str = ""
    type: str = ""


class MetafieldList(sdl.Entity):
    items: list[Metafield] = []


class ListMetafieldsParams(ConnParams):
    owner_id: str = Field(..., description="GID of the owning resource (Product, Order, Customer, etc.).")


class SetMetafieldParams(ConnParams):
    owner_id: str = Field(..., description="GID of the owning resource.")
    namespace: str = Field(..., description="Metafield namespace, e.g. 'custom'.")
    key: str = Field(..., description="Metafield key, e.g. 'care_instructions'.")
    value: str = Field(..., description="Metafield value.")
    type: str = Field("single_line_text_field", description="Metafield type, e.g. single_line_text_field, number_integer, boolean, json.")


class DeleteMetafieldParams(ConnParams):
    metafield_id: str = Field(..., description="Metafield GID to delete.")


# ──────────────────────────────────────────────────────────────────────────
# Webhooks
# ──────────────────────────────────────────────────────────────────────────


class WebhookSubscription(sdl.Entity):
    id: str = ""
    topic: str = ""
    callback_url: str = ""
    format: str = ""


class WebhookList(sdl.Entity):
    items: list[WebhookSubscription] = []


class ListWebhooksParams(ConnParams):
    pass


class CreateWebhookParams(ConnParams):
    topic: str = Field(..., description="Webhook topic, e.g. ORDERS_CREATE, PRODUCTS_UPDATE, APP_UNINSTALLED.")
    callback_url: str = Field(..., description="HTTPS URL Shopify will POST event payloads to.")


class DeleteWebhookParams(ConnParams):
    webhook_id: str = Field(..., description="WebhookSubscription GID to delete.")


# ──────────────────────────────────────────────────────────────────────────
# Bulk Operations (Ярус 3 value-add)
# ──────────────────────────────────────────────────────────────────────────


class RunBulkQueryParams(ConnParams):
    query: str = Field(..., description="A GraphQL query to run as a bulk operation (for exporting large datasets).")


class BulkOperationStatus(sdl.Entity):
    id: str = ""
    status: str = ""
    object_count: int = 0
    url: str = ""
    error_code: str = ""


class GetBulkOperationStatusParams(ConnParams):
    pass


class CancelBulkOperationParams(ConnParams):
    operation_id: str = Field(..., description="BulkOperation GID to cancel.")


# ──────────────────────────────────────────────────────────────────────────
# Value-add reports (Ярус 3)
# ──────────────────────────────────────────────────────────────────────────


class LowStockRow(sdl.Entity):
    product_title: str = ""
    variant_title: str = ""
    sku: str = ""
    available: int = 0
    location: str = ""


class LowStockReport(sdl.Entity):
    rows: list[LowStockRow] = []
    threshold: int = 0


class GetLowStockReportParams(ConnParams):
    threshold: int = Field(5, ge=0, description="Report variants at or below this available quantity.")
    limit: int = Field(250, ge=1, le=250, description="Max products to scan.")


class StoreSummary(sdl.Entity):
    products_count: int = 0
    orders_count_last_30d: int = 0
    revenue_last_30d: str = ""
    customers_count: int = 0
    open_orders_count: int = 0


class GetStoreSummaryParams(ConnParams):
    pass
