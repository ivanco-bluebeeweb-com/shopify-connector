"""Panel UI -- connections list/connect form + store snapshot.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule (same convention as MuleSoft
Connector's / Power Automate Connector's / n8n Connector's panels.py).

Every section (connections, connect form, store snapshot) is a plain
ui.Stack, content stacked vertically and left-aligned, sections separated
by ui.Divider() -- no Card border/background/shadow anywhere in this slot.
Disconnect lives only in the "App settings" screen (panels_settings.py).
The one secondary "App settings" button is always the LAST element at the
bottom of the sidebar.

WHY A FULL FORM (shop domain + access token), NOT A SINGLE TOKEN FIELD
LIKE n8n/Make.com.

A Shopify Admin API access token is meaningless without knowing which
shop it belongs to -- every GraphQL call is made against
`https://{shop}.myshopify.com/admin/api/...`. The form therefore asks for
both fields plus an optional label, with a help dialog explaining exactly
where to create a Custom App and get its token (Settings > Apps and sales
channels > Develop apps), the same shape as MuleSoft Connector's 4-field
form.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers as h


def _settings_button() -> ui.UINode:
    """The one required secondary entry point into the settings screen --
    always the last element at the bottom of the sidebar."""
    return ui.Button(
        "App settings", variant="secondary", size="sm", full_width=True,
        icon="settings", on_click=ui.Call("__panel__shopify_settings"),
    )


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("label") or c.get("shop_domain", "")
    return ui.Stack(direction="v", gap=1, children=[
        ui.Text(label, variant="body"),
        ui.Text(c.get("shop_domain", ""), variant="caption"),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No stores connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _connect_section() -> ui.UINode:
    """Plain content, no Card wrapper. Stretched full-width per
    UI_INTERFACE_STANDARD.md (2026-08-20). No intro heading/description
    text here -- the Custom App walkthrough lives ONLY in
    shopify_connect_help's modal (button below opens it); repeating it
    here would duplicate that instruction."""
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Button("How do I set this up?", variant="ghost", size="sm",
                  icon="HelpCircle",
                  on_click=ui.Call("__panel__shopify_connect_help")),
        ui.Form(
            action="connect_shopify",
            submit_label="Verify and connect",
            children=[
                ui.Stack(direction="v", gap=1, children=[
                    ui.Text("Shop domain", variant="caption"),
                    ui.Input(param_name="shop_domain", placeholder="my-store.myshopify.com"),
                ]),
                ui.Stack(direction="v", gap=1, children=[
                    ui.Text("Admin API access token", variant="caption"),
                    ui.Password(param_name="access_token",
                                 placeholder="shpat_..."),
                ]),
                ui.Stack(direction="v", gap=1, children=[
                    ui.Text("Label (optional)", variant="caption"),
                    ui.Input(param_name="label", placeholder="e.g. Main store"),
                ]),
            ],
        ),
    ])


@ext.panel("shopify_connect", slot="left", title="Shopify", icon="🛍️",
           default_width=320, min_width=260, max_width=420)
async def shopify_connect_panel(ctx, **kwargs) -> object:
    connections = await h._load_connections(ctx)
    connected = bool(connections)

    header = ui.Header(text="Shopify", level=2,
                        subtitle="Manage your Shopify store's catalog, orders, and customers from Imperal")

    if not connected:
        return ui.Stack(direction="v", gap=4, align="stretch", children=[
            header,
            _connect_section(),
            ui.Divider(),
            _settings_button(),
        ])

    summary_rows: list[ui.UINode] = []
    first = connections[0]
    try:
        conn, token, err = await h._resolve_or_error(ctx, first.get("id", ""))
        if not err:
            data = await h.sc.graphql(ctx, token, conn["shop_domain"], "query { shop { name currencyCode } }")
            shop = data.get("shop") or {}
            summary_rows.append(ui.Text(f"{shop.get('name', '')} · {shop.get('currencyCode', '')}", variant="caption"))
    except Exception:
        pass

    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        header,
        ui.Text("Connected stores", variant="subtitle"),
        _connections_section(connections),
        *summary_rows,
        ui.Divider(),
        ui.Button("View orders", variant="primary", size="sm", full_width=True,
                  icon="ShoppingCart", on_click=ui.Call("__panel__shopify_center")),
        ui.Divider(),
        _connect_section(),
        ui.Divider(),
        _settings_button(),
    ])


@ext.panel("shopify_connect_help", slot="center",
           title="How to connect Shopify", center_overlay=True)
async def shopify_connect_help(ctx, **kwargs) -> object:
    content = ui.Stack(direction="v", gap=3, children=[
        ui.Text("1. In your Shopify admin, go to Settings > Apps and sales channels > Develop apps."),
        ui.Text("2. Click \"Allow custom app development\" if this is the first custom app on the store, then \"Create an app\"."),
        ui.Text("3. Open the app's \"Configuration\" tab and grant the Admin API access scopes you want to use (e.g. read/write products, orders, customers, inventory, discounts)."),
        ui.Text("4. Go to the \"API credentials\" tab and click \"Install app\"."),
        ui.Text("5. Copy the Admin API access token shown right after install -- Shopify only shows it once."),
        ui.Text("6. Paste your shop's *.myshopify.com domain and that access token into the form."),
        ui.Divider(),
        ui.Alert(
            title="Your own store, your own token",
            message=(
                "Imperal never sees or stores your Shopify login. The "
                "Custom App access token you paste here talks directly to "
                "your store's Admin API, scoped to only the permissions "
                "you granted it."
            ),
            type="info",
        ),
        ui.Divider(),
        ui.Link(
            label="Open Shopify's official Custom App guide",
            href="https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/generate-app-access-tokens-admin",
        ),
    ])
    return ui.Dialog(
        title="How to connect Shopify",
        content=content,
        confirm_label="",
        cancel_label="Close",
    )


_ORDER_STATUS_COLOR = {
    "PAID": "green", "PARTIALLY_PAID": "yellow", "PENDING": "yellow",
    "REFUNDED": "gray", "VOIDED": "red", "FULFILLED": "green",
    "UNFULFILLED": "yellow", "PARTIALLY_FULFILLED": "yellow",
}


def _order_row(o) -> dict:
    return {
        "name": o.name, "email": o.email or "—",
        "total": f"{o.total_price} {o.currency}".strip(),
        "financial_status": o.financial_status or "—",
        "fulfillment_status": o.fulfillment_status or "—",
        "created_at": (o.created_at or "")[:10],
        "order_id": o.id,
    }


@ext.panel("shopify_center", slot="center", title="Shopify", icon="🛍️", center_overlay=True)
async def shopify_center_panel(ctx, order_id: str = "", **kwargs) -> object:
    """Post-connect main screen: Orders Dashboard, or Order Detail when
    `order_id` is passed (master-detail via the same panel_id, per
    UI_COMPONENT_VOCABULARY.md §3). Falls back to the connect prompt if
    no store is connected yet."""
    connections = await h._load_connections(ctx)
    if not connections:
        return ui.Empty(
            message="Connect a Shopify store from the sidebar to see your orders here.",
            icon="🛍️",
        )

    if order_id:
        return await _order_detail(ctx, order_id)
    return await _orders_dashboard(ctx)


async def _orders_dashboard(ctx) -> ui.UINode:
    summary_result = await h.get_store_summary(ctx, h.GetStoreSummaryParams())
    stats: list[ui.UINode] = []
    if summary_result.success and summary_result.data:
        s = summary_result.data
        stats = [
            ui.Stat(label="Open orders", value=str(s.open_orders_count)),
            ui.Stat(label="Orders (30d)", value=str(s.orders_count_last_30d)),
            ui.Stat(label="Revenue (30d)", value=s.revenue_last_30d or "—"),
            ui.Stat(label="Customers", value=str(s.customers_count)),
        ]

    orders_result = await h.list_orders(ctx, h.ListOrdersParams(limit=50))
    if not orders_result.success:
        return ui.Stack(direction="v", gap=4, children=[
            *([ui.Stats(children=stats)] if stats else []),
            ui.Error(message=orders_result.error or "Could not load orders.",
                     retry=ui.Call("__panel__shopify_center")),
        ])

    orders = orders_result.data.items if orders_result.data else []
    if not orders:
        return ui.Stack(direction="v", gap=4, children=[
            *([ui.Stats(children=stats)] if stats else []),
            ui.Empty(message="No orders yet -- they will appear here as customers check out.", icon="🧾"),
        ])

    columns = [
        ui.DataColumn("name", "Order", sortable=True),
        ui.DataColumn("email", "Customer", sortable=True),
        ui.DataColumn("total", "Total", sortable=True),
        ui.DataColumn("financial_status", "Payment", sortable=True),
        ui.DataColumn("fulfillment_status", "Fulfillment", sortable=True),
        ui.DataColumn("created_at", "Date", sortable=True),
    ]
    table = ui.DataTable(
        columns=columns,
        rows=[_order_row(o) for o in orders],
        on_row_click=ui.Call("__panel__shopify_center", order_id=""),
    )
    return ui.Stack(direction="v", gap=4, children=[
        ui.Header(text="Orders", level=2),
        *([ui.Stats(children=stats)] if stats else []),
        table,
    ])


async def _order_detail(ctx, order_id: str) -> ui.UINode:
    result = await h.get_order(ctx, h.GetOrderParams(order_id=order_id))
    if not result.success or not result.data:
        return ui.Error(
            message=result.error or "Could not load this order.",
            retry=ui.Call("__panel__shopify_center"),
        )
    o = result.data
    items_columns = [
        ui.DataColumn("title", "Product", sortable=False),
        ui.DataColumn("quantity", "Qty", sortable=False),
        ui.DataColumn("price", "Price", sortable=False),
    ]
    items_rows = [
        {"title": li.title, "quantity": str(li.quantity), "price": li.price}
        for li in (o.line_items or [])
    ]
    return ui.Stack(direction="v", gap=4, children=[
        ui.Button("← Back to orders", variant="ghost", size="sm",
                  on_click=ui.Call("__panel__shopify_center")),
        ui.Header(text=o.name, level=2,
                  subtitle=f"{o.total_price} {o.currency}".strip()),
        ui.KeyValue(items=[
            {"key": "Customer", "value": o.email or "—"},
            {"key": "Payment status", "value": o.financial_status or "—"},
            {"key": "Fulfillment status", "value": o.fulfillment_status or "—"},
            {"key": "Placed", "value": (o.created_at or "")[:10]},
        ]),
        ui.Text("Line items", variant="heading"),
        ui.DataTable(columns=items_columns, rows=items_rows) if items_rows
        else ui.Text("No line items on this order.", variant="caption"),
        ui.Row(children=[
            ui.Button("Cancel order", variant="destructive", size="sm",
                      on_click=ui.Call("__panel__shopify_cancel_confirm", order_id=o.id)),
        ]),
    ])


@ext.panel("shopify_cancel_confirm", slot="center", center_overlay=True)
async def shopify_cancel_confirm(ctx, order_id: str = "", **kwargs) -> object:
    """Destructive/financial action -- must go through an explicit Dialog
    per UI_INTERFACE_STANDARD.md, never a direct one-click button action."""
    return ui.Dialog(
        title="Cancel this order?",
        content=ui.Text(
            "This cancels the order in Shopify. Depending on your store's "
            "settings this may restock inventory and notify the customer. "
            "This cannot be undone from here."),
        confirm_label="Cancel order",
        cancel_label="Keep order",
        on_confirm=ui.Call("cancel_order", order_id=order_id),
    )
