"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), same reasoning as MuleSoft Connector /
Power Automate Connector / n8n Connector. The user's Shopify store is
THEIR OWN store -- Imperal cannot and should not broker access to
someone else's Shopify account centrally.

WHY CUSTOM APP ADMIN API ACCESS TOKEN, NOT OAUTH AUTHORIZATION CODE GRANT.

Shopify supports two paths to an Admin API access token: (1) building a
public/OAuth app that goes through Shopify's own App Store review and a
full authorization-code redirect dance, or (2) a store owner creating a
**Custom App** directly in their own admin (Settings > Apps and sales
channels > Develop apps), picking access scopes, and getting a static
Admin API access token immediately -- no external review, no redirect
flow (shopify.dev/docs/apps/build/authentication-authorization/access-
tokens/generate-app-access-tokens-admin, confirmed during Discovery
2026-08-20). Exactly the same "instantly available, no chicken-and-egg"
reasoning that led MuleSoft Connector to Connected Apps and Power
Automate Connector to an Azure AD App Registration -- a public OAuth app
would require Imperal to go through Shopify's own Partner/App Store
review before a single real API call could be made. The connector
therefore asks for the shop's *.myshopify.com domain plus the Custom
App's Admin API access token.

WHY `write_mode="both"`, SAME REASONING AS MuleSoft/n8n/Make.com/Power
Automate CONNECTOR.

Declaring `write_mode="user"` would mean only the platform's generic
Secrets screen could write these -- leaving a first-time user with no
in-app screen explaining what a Custom App even is or how to create one.
`"both"` keeps the generic Secrets screen as a fallback while letting
`connect_shopify` be the friendly guided path.

WHY SCOPE IS PER-ACCOUNT, NOT APP-LEVEL, SAME AS MuleSoft/n8n/Make.com/
Power Automate CONNECTOR.

Different Imperal users must never see each other's store connections.
Secrets are stored per-account, and a user may connect MULTIPLE Shopify
stores (e.g. an agency managing several clients' shops) --
`shopify_connections` holds a JSON array, matching the multi-connection
shape of every other BYOK connector in the portfolio.
"""
from __future__ import annotations

from imperal_sdk import ChatExtension, Extension

ext = Extension(
    "shopify-connector",
    version="0.1.0",
    display_name="Shopify",
    description=(
        "Connect your own Shopify store(s) via a Custom App Admin API access "
        "token. Manage products, variants, collections, orders, draft orders, "
        "refunds, customers, inventory across locations, fulfillment orders, "
        "discounts (code and automatic), metafields, webhooks, and bulk data "
        "exports through the GraphQL Admin API."
    ),
    icon="icon.svg",
    capabilities=[
        "shopify:read",
        "shopify:write",
    ],
    actions_explicit=True,
    system=False,
)

chat = ChatExtension(
    ext,
    tool_name="shopify",
    description=(
        "Shopify Connector -- connect your own Shopify store(s) via a Custom "
        "App Admin API access token, then manage products/variants/"
        "collections, orders/draft orders/refunds/fulfillment, customers, "
        "inventory across locations, discounts, metafields, webhooks, and "
        "run bulk data exports and value-add store reports."
    ),
)

ext.secret(
    "shopify_connections",
    (
        "Your connected Shopify stores -- stored as a JSON array, one entry "
        "per store, each with its shop domain and Custom App Admin API "
        "access token. Managed through connect_shopify / disconnect_shopify "
        "-- you should not need to edit this directly."
    ),
    required=True,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=180,
)(lambda: None)


@ext.health_check
async def health_check(ctx) -> dict:
    """Fast configuration health; no third-party call -- just confirms at
    least one store connection is stored, same shape as MuleSoft's/Power
    Automate's health_check."""
    import json as _json
    raw = await ctx.secrets.get("shopify_connections")
    try:
        count = len(_json.loads(raw)) if raw else 0
    except Exception:
        count = 0
    return {
        "healthy": True,
        "detail": (
            f"{count} Shopify store(s) connected." if count
            else "Not connected yet -- run connect_shopify."
        ),
    }
