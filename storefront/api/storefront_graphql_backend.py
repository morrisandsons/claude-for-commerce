# SPDX-License-Identifier: Apache-2.0
"""``StorefrontBackend`` over a live Shopify shop's plain Storefront GraphQL API —
no UCP, no Agentic Storefronts feature flag required. Works against any store with a
Storefront API access token: a real store, a development/sandbox store, or a
mock.shop catalog. Catalog reads use ``products``/``product`` queries; the cart uses
the standard ``cartCreate``/``cartLinesAdd``/``cartLinesUpdate``/``cartLinesRemove``
mutations, and the cart's own ``checkoutUrl`` is the handoff — no separate checkout
staging needed, unlike the UCP path. Orders require a customer login flow this
backend does not implement, so ``get_orders``/``get_order`` return nothing; that's a
deliberate scope cut, not a bug — add a real Customer Account API integration later
if order tracking is needed.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from shopping_agent import (
    Cart,
    CartItem,
    FulfillmentOption,
    Order,
    Policy,
    Product,
    ProductDetails,
    SearchFilters,
    ShoppingSessionContext,
    StorefrontBackend,
    UserPreferences,
)

logger = logging.getLogger(__name__)

STOREFRONT_API_VERSION = "2026-07"
_TIMEOUT = httpx.Timeout(20.0)
_VARIANT_PREFIX = "gid://shopify/ProductVariant/"
_CART_PREFIX = "gid://shopify/Cart/"


def shop_domain_from_env() -> str:
    return os.environ.get("SHOP_DOMAIN", "demostore.mock.shop")


def storefront_token_from_env() -> str | None:
    return os.environ.get("SHOPIFY_STOREFRONT_TOKEN")


def cart_gid(value: str) -> str:
    """Same normalization as the UCP backend's helper: the ``cart`` cookie's raw
    token, or the full gid, both become ``gid://shopify/Cart/<token>``."""
    token = value.strip()
    return token if token.startswith(_CART_PREFIX) else f"{_CART_PREFIX}{token}"


_PRODUCT_FIELDS = """
  id
  title
  handle
  descriptionHtml
  productType
  tags
  featuredImage { url }
  priceRange { minVariantPrice { amount currencyCode } }
  variants(first: 20) {
    edges {
      node {
        id
        title
        availableForSale
        quantityAvailable
        price { amount currencyCode }
        image { url }
        selectedOptions { name value }
      }
    }
  }
"""

SEARCH_QUERY = f"""
query Search($query: String!, $first: Int!) {{
  products(first: $first, query: $query) {{
    edges {{ node {{ {_PRODUCT_FIELDS} }} }}
  }}
}}
"""

PRODUCT_BY_ID_QUERY = f"""
query ProductById($id: ID!) {{
  product(id: $id) {{ {_PRODUCT_FIELDS} }}
}}
"""

CART_FIELDS = """
  id
  checkoutUrl
  totalQuantity
  cost { subtotalAmount { amount currencyCode } }
  lines(first: 50) {
    edges {
      node {
        id
        quantity
        merchandise {
          ... on ProductVariant {
            id
            title
            price { amount currencyCode }
            image { url }
            product { title }
          }
        }
      }
    }
  }
"""

CART_CREATE = f"""
mutation CartCreate($lines: [CartLineInput!]!) {{
  cartCreate(input: {{ lines: $lines }}) {{
    cart {{ {CART_FIELDS} }}
    userErrors {{ field message }}
  }}
}}
"""

CART_QUERY = f"""
query CartQuery($id: ID!) {{
  cart(id: $id) {{ {CART_FIELDS} }}
}}
"""

CART_LINES_ADD = f"""
mutation CartLinesAdd($cartId: ID!, $lines: [CartLineInput!]!) {{
  cartLinesAdd(cartId: $cartId, lines: $lines) {{
    cart {{ {CART_FIELDS} }}
    userErrors {{ field message }}
  }}
}}
"""

CART_LINES_UPDATE = f"""
mutation CartLinesUpdate($cartId: ID!, $lines: [CartLineUpdateInput!]!) {{
  cartLinesUpdate(cartId: $cartId, lines: $lines) {{
    cart {{ {CART_FIELDS} }}
    userErrors {{ field message }}
  }}
}}
"""

CART_LINES_REMOVE = f"""
mutation CartLinesRemove($cartId: ID!, $lineIds: [ID!]!) {{
  cartLinesRemove(cartId: $cartId, lineIds: $lineIds) {{
    cart {{ {CART_FIELDS} }}
    userErrors {{ field message }}
  }}
}}
"""

NODE_URL_QUERY = """
query NodeUrl($id: ID!) {
  node(id: $id) {
    ... on Product { handle }
    ... on ProductVariant { product { handle } }
  }
}
"""

POLICIES_QUERY = """
{
  shop {
    shippingPolicy { title body }
    refundPolicy { title body }
    privacyPolicy { title body }
    termsOfService { title body }
  }
}
"""

_TAG = re.compile(r"<[^>]+>")


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", _TAG.sub(" ", value)).strip() or None


@dataclass
class _SessionState:
    cart_id: str | None = None
    checkout_url: str | None = None
    currency: str = "USD"
    default_variant: dict[str, str] = field(default_factory=dict)  # product gid -> variant gid
    lines: dict[str, tuple[str, int]] = field(default_factory=dict)  # variant gid -> (line id, qty)
    variant_of: dict[str, str] = field(default_factory=dict)  # variant gid -> product gid


class GraphQLError(RuntimeError):
    """The Storefront API returned a top-level ``errors`` array or ``userErrors``."""


class ShopifyStorefrontAPIBackend(StorefrontBackend):
    def __init__(
        self,
        shop_domain: str | None = None,
        access_token: str | None = None,
        http: httpx.AsyncClient | None = None,
        store_name: str = "Shopify store",
    ) -> None:
        self.shop_domain = shop_domain or shop_domain_from_env()
        self.access_token = access_token or storefront_token_from_env()
        if not self.access_token:
            raise RuntimeError(
                "SHOPIFY_STOREFRONT_TOKEN is required for ShopifyStorefrontAPIBackend "
                "(Settings -> Apps and sales channels -> Develop apps -> configure the "
                "Storefront API and install the app to get one)."
            )
        self.store_name = store_name
        self._url = f"https://{self.shop_domain}/api/{STOREFRONT_API_VERSION}/graphql.json"
        self._http = http or httpx.AsyncClient(timeout=_TIMEOUT)
        self._sessions: dict[str, _SessionState] = {}
        # Display caches, same shape as the UCP backend's, so catalog_warmup.py
        # (if used) and any /api/products route work unchanged.
        self.products: dict[str, ProductDetails] = {}
        self.default_variants: dict[str, str] = {}
        self._variant_images: dict[str, str] = {}
        self._handles: dict[str, str] = {}  # product/variant gid -> handle, for building real page URLs

    # -- Session bookkeeping, mirroring the UCP backend's public surface ----------

    def _state(self, session: ShoppingSessionContext) -> _SessionState:
        return self._sessions.setdefault(session.session_id, _SessionState())

    def reset_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def cart_id_for(self, session_id: str) -> str | None:
        state = self._sessions.get(session_id)
        return state.cart_id if state else None

    async def checkout_url_for(self, session_id: str) -> str | None:
        state = self._sessions.get(session_id)
        return state.checkout_url if state else None

    async def attach_cart(self, session_id: str, cart_id: str) -> Cart | None:
        payload = await self._graphql(CART_QUERY, {"id": cart_gid(cart_id)})
        cart = payload.get("cart")
        if cart is None:
            return None
        state = self._sessions.setdefault(session_id, _SessionState())
        return self._map_cart(state, cart)

    # -- GraphQL plumbing -----------------------------------------------------------

    async def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = await self._http.post(
            self._url,
            json={"query": query, "variables": variables},
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Storefront-Access-Token": self.access_token,
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            raise GraphQLError(str(body["errors"]))
        return body["data"]

    @staticmethod
    def _check_user_errors(payload: dict[str, Any], key: str) -> dict[str, Any]:
        result = payload[key]
        if result.get("userErrors"):
            raise GraphQLError(str(result["userErrors"]))
        return result

    # -- Catalog ---------------------------------------------------------------

    async def search_products(
        self,
        session: ShoppingSessionContext,
        query: str,
        filters: SearchFilters | None = None,
        limit: int = 8,
    ) -> list[Product]:
        payload = await self._graphql(SEARCH_QUERY, {"query": query, "first": limit})
        state = self._state(session)
        edges = payload.get("products", {}).get("edges", [])
        return [self._remember_product(state, edge["node"]) for edge in edges]

    async def get_product_details(
        self, session: ShoppingSessionContext, product_id: str
    ) -> ProductDetails | None:
        state = self._state(session)
        if product_id.startswith(_VARIANT_PREFIX):
            parent_id = state.variant_of.get(product_id)
            if parent_id is None:
                return None
            details = self.products.get(parent_id) or await self.get_product_details(
                session, parent_id
            )
            if details is None:
                return None
            for variant in details.variants:
                if variant.product_id == product_id:
                    return ProductDetails(
                        **variant.model_dump(), long_description=details.long_description
                    )
            return None
        payload = await self._graphql(PRODUCT_BY_ID_QUERY, {"id": product_id})
        record = payload.get("product")
        if not record:
            return None
        return self._remember_product(state, record)

    def _remember_product(self, state: _SessionState, record: dict[str, Any]) -> ProductDetails:
        product_id = record["id"]
        handle = record.get("handle")
        price = float(record["priceRange"]["minVariantPrice"]["amount"])
        currency = record["priceRange"]["minVariantPrice"]["currencyCode"]
        description = _strip_html(record.get("descriptionHtml"))
        variants = [
            self._map_variant(record, edge["node"])
            for edge in record.get("variants", {}).get("edges", [])
        ]
        existing = self.products.get(product_id)
        if existing:
            merged = {v.product_id: v for v in existing.variants}
            merged.update({v.product_id: v for v in variants})
            variants = list(merged.values())
        available = [v for v in variants if v.in_stock]
        details = ProductDetails(
            product_id=product_id,
            title=record["title"],
            price=price,
            currency=currency,
            image_url=(record.get("featuredImage") or {}).get("url"),
            category=record.get("productType") or (record.get("tags") or [None])[0],
            in_stock=bool(available) if variants else True,
            short_description=description[:200] if description else None,
            long_description=description,
            variants=variants,
        )
        state.currency = currency
        if handle:
            self._handles[product_id] = handle
        for variant in variants:
            state.variant_of[variant.product_id] = product_id
            if variant.image_url:
                self._variant_images[variant.product_id] = variant.image_url
            if handle:
                self._handles[variant.product_id] = handle
        if available or variants:
            state.default_variant[product_id] = (available or variants)[0].product_id
            self.default_variants[product_id] = state.default_variant[product_id]
        self.products[product_id] = details
        return details

    async def get_product_url(self, product_id: str, include_variant: bool = True) -> str | None:
        """A real, relative /products/... URL for a product or variant id. Checks the
        in-memory handle cache first (fast, no network); if that's cold — the id was
        never seen this process, or the process restarted and lost its cache — falls
        back to a live, generic lookup by id so this doesn't depend on the exact
        history of what's been searched this process's lifetime.

        include_variant=False always returns the bare product page, even for a
        variant id — used when several variant-level picks all belong to the same
        product (e.g. discussing colour options), so callers can de-duplicate down
        to one link per product rather than one per colour."""
        handle = self._handles.get(product_id)
        if not handle:
            try:
                if product_id.startswith(_VARIANT_PREFIX):
                    # No dedicated "single variant" root query exists in the
                    # Storefront API — node() is the only way to resolve a
                    # lone variant id generically.
                    payload = await self._graphql(NODE_URL_QUERY, {"id": product_id})
                    node = payload.get("node") or {}
                    handle = (node.get("product") or {}).get("handle")
                else:
                    # Reuse the same product(id:) query already proven
                    # reliable elsewhere in this file (get_product_details),
                    # rather than the more exotic node() query — which,
                    # for at least one real product id, returned nothing
                    # usable with no exception raised at all, an unresolved
                    # discrepancy not worth chasing further when a
                    # known-working alternative already exists for this case.
                    payload = await self._graphql(PRODUCT_BY_ID_QUERY, {"id": product_id})
                    record = payload.get("product")
                    handle = record.get("handle") if record else None
                if handle:
                    self._handles[product_id] = handle
            except Exception as exc:  # noqa: BLE001 - deliberately broad: this
                # fallback should degrade to "no chip" rather than crash the
                # request, whatever specifically goes wrong. The logging
                # above is what makes that safe rather than silent.
                # Don't swallow the real reason — an opaque 404 with no log
                # trail is exactly what made the last failure hard to
                # diagnose. Now the actual Shopify error (bad query, missing
                # scope, whatever it turns out to be) lands in the server
                # logs instead of disappearing.
                logger.warning(
                    "get_product_url: node() fallback failed for %s: %s", product_id, exc
                )
                handle = None
        if not handle:
            return None
        if product_id.startswith(_VARIANT_PREFIX) and include_variant:
            numeric_variant = product_id.rsplit("/", 1)[-1]
            return f"/products/{handle}?variant={numeric_variant}"
        return f"/products/{handle}"

    def _map_variant(self, record: dict[str, Any], variant: dict[str, Any]) -> Product:
        options = {opt["name"]: opt["value"] for opt in variant.get("selectedOptions") or []}
        return Product(
            product_id=variant["id"],
            title=f"{record['title']} — {variant['title']}",
            price=float(variant["price"]["amount"]),
            currency=variant["price"]["currencyCode"],
            image_url=(variant.get("image") or {}).get("url")
            or (record.get("featuredImage") or {}).get("url"),
            attributes=options,
            in_stock=bool(variant.get("availableForSale")),
        )

    # -- Cart --------------------------------------------------------------------

    async def get_cart(self, session: ShoppingSessionContext) -> Cart:
        state = self._state(session)
        if state.cart_id is None:
            return Cart(currency=state.currency)
        payload = await self._graphql(CART_QUERY, {"id": state.cart_id})
        cart = payload.get("cart")
        if cart is None:
            self._drop_cart(state)
            return Cart(currency=state.currency)
        return self._map_cart(state, cart)

    async def add_to_cart(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        state = self._state(session)
        variant_id = await self._resolve_variant(session, state, product_id)
        if state.cart_id is None:
            payload = await self._graphql(
                CART_CREATE, {"lines": [{"merchandiseId": variant_id, "quantity": quantity}]}
            )
            result = self._check_user_errors(payload, "cartCreate")
            cart = self._map_cart(state, result["cart"])
            self._check_landed_quantity(state, variant_id, quantity)
            return cart
        already = state.lines.get(variant_id)
        if already:
            line_id, existing_qty = already
            expected = existing_qty + quantity
            payload = await self._graphql(
                CART_LINES_UPDATE,
                {
                    "cartId": state.cart_id,
                    "lines": [{"id": line_id, "quantity": expected}],
                },
            )
            result = self._check_user_errors(payload, "cartLinesUpdate")
        else:
            expected = quantity
            payload = await self._graphql(
                CART_LINES_ADD,
                {
                    "cartId": state.cart_id,
                    "lines": [{"merchandiseId": variant_id, "quantity": quantity}],
                },
            )
            result = self._check_user_errors(payload, "cartLinesAdd")
        cart = self._map_cart(state, result["cart"])
        self._check_landed_quantity(state, variant_id, expected)
        return cart

    def _check_landed_quantity(
        self, state: _SessionState, variant_id: str, expected: int
    ) -> None:
        """Shopify's cart mutations can succeed with no userErrors while silently
        capping the actual line quantity below what was requested (typically: not
        enough sellable stock right now). Catch that here rather than letting the
        agent believe a full add_to_cart succeeded when it didn't."""
        landed = state.lines.get(variant_id)
        landed_qty = landed[1] if landed else 0
        if landed_qty < expected:
            raise GraphQLError(
                f"Shopify accepted the request but only {landed_qty} of the requested "
                f"{expected} could actually be added to the cart for this variant — "
                "likely limited available stock right now. Tell the customer the real "
                "number that landed, don't imply the full amount was added."
            )

    async def update_cart_item(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        return await self._set_line(session, product_id, quantity)

    async def remove_from_cart(self, session: ShoppingSessionContext, product_id: str) -> Cart:
        state = self._state(session)
        variant_id = (
            product_id
            if product_id in state.lines
            else state.default_variant.get(product_id, product_id)
        )
        if state.cart_id is None or variant_id not in state.lines:
            return await self.get_cart(session)
        line_id, _ = state.lines[variant_id]
        payload = await self._graphql(
            CART_LINES_REMOVE, {"cartId": state.cart_id, "lineIds": [line_id]}
        )
        result = self._check_user_errors(payload, "cartLinesRemove")
        return self._map_cart(state, result["cart"])

    async def _set_line(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        state = self._state(session)
        variant_id = (
            product_id
            if product_id in state.lines
            else state.default_variant.get(product_id, product_id)
        )
        if state.cart_id is None or variant_id not in state.lines:
            return await self.get_cart(session)
        line_id, _ = state.lines[variant_id]
        payload = await self._graphql(
            CART_LINES_UPDATE,
            {"cartId": state.cart_id, "lines": [{"id": line_id, "quantity": quantity}]},
        )
        result = self._check_user_errors(payload, "cartLinesUpdate")
        return self._map_cart(state, result["cart"])

    def _drop_cart(self, state: _SessionState) -> None:
        state.cart_id = None
        state.checkout_url = None
        state.lines = {}

    async def _resolve_variant(
        self, session: ShoppingSessionContext, state: _SessionState, product_id: str
    ) -> str:
        if product_id.startswith(_VARIANT_PREFIX):
            return product_id
        if product_id not in state.default_variant and product_id not in self.default_variants:
            await self.get_product_details(session, product_id)
        variant_id = state.default_variant.get(product_id) or self.default_variants.get(product_id)
        if variant_id is None:
            raise GraphQLError(f"No purchasable variant for {product_id}.")
        return variant_id

    def _map_cart(self, state: _SessionState, cart: dict[str, Any]) -> Cart:
        state.cart_id = cart["id"]
        state.checkout_url = cart.get("checkoutUrl") or state.checkout_url
        state.lines = {}
        items: list[CartItem] = []
        currency = state.currency
        for edge in cart.get("lines", {}).get("edges", []):
            line = edge["node"]
            merch = line.get("merchandise") or {}
            variant_id = merch.get("id")
            if variant_id is None:
                continue
            qty = line["quantity"]
            if qty <= 0:
                # Shopify accepted the mutation with no userErrors, but capped the
                # sellable quantity to zero (typically: requested amount exceeds
                # what's actually available to sell right now). Drop the empty
                # line rather than crash, and don't remember a line id for it —
                # there's nothing here for update/remove to act on.
                state.lines.pop(variant_id, None)
                continue
            state.lines[variant_id] = (line["id"], qty)
            price_money = merch.get("price") or {}
            currency = price_money.get("currencyCode", currency)
            items.append(
                CartItem(
                    product_id=variant_id,
                    title=f"{(merch.get('product') or {}).get('title', '')} — {merch.get('title', '')}".strip(
                        " —"
                    ),
                    price=float(price_money.get("amount", 0)),
                    quantity=qty,
                    image_url=(merch.get("image") or {}).get("url")
                    or self._variant_images.get(variant_id),
                )
            )
        state.currency = currency
        return Cart(items=items, currency=currency)

    # -- Customer context, orders, policies, fulfillment ---------------------------

    async def get_preferences(self, session: ShoppingSessionContext) -> UserPreferences:
        return UserPreferences(user_id=session.user_id, display_name="Guest")

    async def get_orders(self, session: ShoppingSessionContext, limit: int = 5) -> list[Order]:
        # Requires a Customer Account API login flow this backend doesn't implement.
        return []

    async def get_order(self, session: ShoppingSessionContext, order_id: str) -> Order | None:
        return None

    async def search_policies(self, session: ShoppingSessionContext, query: str) -> list[Policy]:
        payload = await self._graphql(POLICIES_QUERY, {})
        shop = payload.get("shop", {})
        query_lower = query.lower()
        policies: list[Policy] = []
        for key in ("shippingPolicy", "refundPolicy", "privacyPolicy", "termsOfService"):
            entry = shop.get(key)
            if not entry:
                continue
            title = entry.get("title") or key
            body = _strip_html(entry.get("body")) or ""
            if query_lower in title.lower() or query_lower in body.lower() or not query.strip():
                policies.append(Policy(policy_id=key, title=title, content=body))
        return policies

    async def get_fulfillment_options(
        self, session: ShoppingSessionContext, product_ids: list[str]
    ) -> list[FulfillmentOption]:
        return []