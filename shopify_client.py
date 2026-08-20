"""Shopify Admin GraphQL API HTTP client -- custom app Admin API access
token auth against the user's OWN Shopify store, thin wrapper around the
GraphQL Admin API endpoint plus bulk operations polling.

WHY CUSTOM APP ACCESS TOKEN, NOT OAUTH AUTHORIZATION CODE -- see app.py
module docstring for the full architectural reasoning (same
"instantly available, no chicken-and-egg" principle as MuleSoft's
Connected App / Power Automate's App Registration / n8n's API key).

WHY GRAPHQL ADMIN API AS THE ONLY SURFACE, NOT REST.

Shopify officially steers all new development toward the GraphQL Admin
API; REST-only resources are explicitly tracked by Shopify's own
"Deprecated API calls" resource as technical debt on a custom app
(shopify.dev/docs/api/admin-rest/latest/resources/deprecated-api-calls,
confirmed during Discovery 2026-08-20). Every operation in this connector
is therefore a single GraphQL query or mutation against one endpoint:
`https://{shop}.myshopify.com/admin/api/{API_VERSION}/graphql.json`.

WHY A PINNED API_VERSION CONSTANT, NOT "latest".

Shopify calendar-versions its API quarterly (YYYY-MM) with ~12 months of
support per version (shopify.dev/docs/api/usage/versioning, confirmed
2026-08-20). Pinning one version in code means behaviour doesn't shift
under us when Shopify rolls a new quarterly release; upgrading is a
one-line change reviewed deliberately, same principle as MuleSoft's
CloudHub API version handling.

WHY COST-BASED THROTTLING IS HANDLED EXPLICITLY, NOT JUST RETRIED BLINDLY.

The GraphQL Admin API uses a leaky-bucket, query-COST based rate limit
(not simple requests-per-second) -- every response carries
`extensions.cost.throttleStatus` (currentlyAvailable / maximumAvailable /
restoreRate). A 429 or a `THROTTLED` top-level error means the bucket is
empty; the client backs off using the actual `restoreRate` from the
response instead of a fixed sleep, so bulk callers (e.g. audit_shop_catalog
walking many pages) behave well instead of hammering a near-empty bucket
(shopify.dev/docs/api/usage/limits, shopify.engineering/rate-limiting-
graphql-apis-calculating-query-complexity, confirmed 2026-08-20).

WHY 401 vs 403 ARE HANDLED DIFFERENTLY, SAME PRINCIPLE AS OTHER
BYOK CONNECTORS IN THIS PORTFOLIO (MuleSoft/n8n/Make/Power Automate).

A 401 means the access token itself is not accepted (revoked, wrong
shop domain, malformed token). A 403 (or a GraphQL-level ACCESS_DENIED
error) means the token is valid but the custom app's approved scopes
don't cover the requested resource -- the user needs to go back into
their Shopify admin and add the missing scope to the custom app, not
reconnect from scratch.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

API_VERSION = "2025-10"
_TIMEOUT = 30


class ClientFail(Exception):
    """Raised for any Shopify Admin API failure -- HTTP-level, GraphQL
    top-level errors, or per-mutation userErrors -- with a `code` hint
    the caller/handler can branch on."""

    def __init__(self, message: str, code: str = "unknown"):
        super().__init__(message)
        self.code = code


def _endpoint(shop_domain: str) -> str:
    shop = shop_domain.strip().lower()
    shop = shop.replace("https://", "").replace("http://", "").rstrip("/")
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"
    return f"https://{shop}/admin/api/{API_VERSION}/graphql.json"


async def graphql(
    ctx,
    access_token: str,
    shop_domain: str,
    query: str,
    variables: dict | None = None,
) -> dict:
    """Run one GraphQL query/mutation against the shop's Admin API.
    Returns the `data` object on success. Raises ClientFail on any
    HTTP-level error, top-level GraphQL `errors`, or THROTTLED response
    (after one backoff+retry using the real restoreRate)."""
    url = _endpoint(shop_domain)
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables or {}}

    for attempt in range(2):
        resp = await ctx.http.post(url, headers=headers, json=payload, timeout=_TIMEOUT)

        if resp.status_code == 401:
            raise ClientFail(
                "Shopify rejected this access token -- it may be revoked, or the shop domain is wrong.",
                code="unauthorized",
            )
        if resp.status_code == 403:
            raise ClientFail(
                "This custom app's access token doesn't have the scope this action needs. "
                "Add the missing scope to the custom app in Shopify admin (Settings > Apps and "
                "sales channels > Develop apps), then reconnect.",
                code="forbidden",
            )
        if resp.status_code == 429:
            if attempt == 0:
                await asyncio.sleep(2.0)
                continue
            raise ClientFail("Shopify's API rate limit is exhausted right now -- try again shortly.", code="throttled")
        if resp.status_code >= 500:
            raise ClientFail(f"Shopify's API returned a server error (HTTP {resp.status_code}).", code="server_error")
        if resp.status_code != 200:
            raise ClientFail(f"Unexpected Shopify API response (HTTP {resp.status_code}): {resp.text[:300]}", code="http_error")

        try:
            body = resp.json()
        except Exception:
            raise ClientFail("Shopify's API returned a non-JSON response.", code="bad_response")

        top_errors = body.get("errors") or []
        if top_errors:
            codes = {
                (e.get("extensions") or {}).get("code", "")
                for e in top_errors
            }
            if "THROTTLED" in codes and attempt == 0:
                cost = (body.get("extensions") or {}).get("cost", {})
                throttle = cost.get("throttleStatus", {})
                restore_rate = throttle.get("restoreRate") or 50
                requested_cost = cost.get("requestedQueryCost") or 50
                wait_s = min(max(requested_cost / max(restore_rate, 1), 0.5), 10.0)
                await asyncio.sleep(wait_s)
                continue
            messages = "; ".join(e.get("message", "") for e in top_errors)
            code = "throttled" if "THROTTLED" in codes else "graphql_error"
            raise ClientFail(f"Shopify API error: {messages}", code=code)

        return body.get("data") or {}

    raise ClientFail("Shopify's API rate limit is exhausted right now -- try again shortly.", code="throttled")


def raise_for_user_errors(data: dict, mutation_key: str, error_field: str = "userErrors") -> list[dict]:
    """Shopify mutations return HTTP 200 + no top-level GraphQL error even
    when the mutation itself failed on business-rule validation -- the
    failure lives in a `userErrors`/`fulfillmentOrders[].validationErrors`
    style list on the mutation's own payload. Raise ClientFail if any are
    present; otherwise return the (empty) list for the caller to ignore."""
    node = (data or {}).get(mutation_key) or {}
    errors = node.get(error_field) or []
    if errors:
        raise ClientFail(
            "Shopify rejected the request: " + "; ".join(
                f"{e.get('field') or ''}: {e.get('message', '')}".strip(": ") for e in errors
            ),
            code="user_errors",
        )
    return errors


def gid(resource_type: str, numeric_or_gid: str | int) -> str:
    """Build a Shopify GlobalID (e.g. gid://shopify/Product/123) from a
    bare numeric id, accepting an already-qualified GID unchanged."""
    s = str(numeric_or_gid)
    if s.startswith("gid://shopify/"):
        return s
    return f"gid://shopify/{resource_type}/{s}"


def numeric_id(global_id: str) -> str:
    """Extract the trailing numeric id from a Shopify GlobalID, or return
    the input unchanged if it wasn't a GID."""
    if isinstance(global_id, str) and global_id.startswith("gid://shopify/"):
        return global_id.rsplit("/", 1)[-1]
    return str(global_id)


async def poll_bulk_operation(ctx, access_token: str, shop_domain: str, *, max_wait_seconds: int = 0) -> dict:
    """Read the current bulk operation status once (or, if max_wait_seconds
    is set, poll until COMPLETED/FAILED/CANCELED or the timeout)."""
    query = """
    query {
      currentBulkOperation {
        id status errorCode createdAt completedAt objectCount fileSize url partialDataUrl
      }
    }
    """
    waited = 0
    interval = 2
    while True:
        data = await graphql(ctx, access_token, shop_domain, query)
        op = data.get("currentBulkOperation") or {}
        status = op.get("status", "")
        if not max_wait_seconds or status in ("COMPLETED", "FAILED", "CANCELED", ""):
            return op
        await asyncio.sleep(interval)
        waited += interval
        if waited >= max_wait_seconds:
            return op
