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


@ext.panel("shopify_center", slot="center", title="Shopify", icon="🛍️", center_overlay=True)
async def shopify_center_panel(ctx, **kwargs) -> object:
    """Base center panel -- per UI_INTERFACE_STANDARD.md (2026-08-20).
    This app has no list/detail content of its own to show in the center
    by default (everything lives in the sidebar). MUST carry
    center_overlay=True: per docs.imperal.io/en/concepts/panels, a plain
    slot="center" panel is registered but the Panel app never fetches it
    at session-init without that flag. Text is the shared canonical
    wording -- must stay identical across every app in this situation."""
    return ui.Empty(
        message="Nothing to show here -- this app is managed entirely from the sidebar.",
        icon="👈",
    )
