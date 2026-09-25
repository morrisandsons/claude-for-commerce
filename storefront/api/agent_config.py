# Copyright 2026 Shopify Inc.
# SPDX-License-Identifier: Apache-2.0

"""The Shopify demo store deployment's shopping agent config: an anonymous storefront
over a live shop, so no disclosures, and ids ground through Shopify's gid form."""

from __future__ import annotations

from shopping_agent import ShoppingAgentConfig


def build_shopping_config(store_name: str) -> ShoppingAgentConfig:
    return ShoppingAgentConfig(
        brand_name=store_name,
        assistant_name="the store assistant",
        brand_voice="friendly, direct, and plain about what this demo store carries",
        # This deployment never adds to cart on the customer's behalf — it helps them
        # decide, then sends them to the real product page to add it themselves.
        # Turning this off removes add_to_cart/update_cart_item/remove_from_cart (and
        # their prompt lines and grounding rules) from every path automatically,
        # rather than trying to block individual tool calls after the fact.
        enable_cart=False,
        domain_search_notes=(
            "The catalog is a live Shopify demo store priced in CAD. A product's "
            "purchasable options (size, color) are its variants in get_product_details; "
            "cart tools are not available in this deployment — once a product (and, if "
            "relevant, its colour/variant) is settled, use navigate_to_product to send "
            "the customer to its real page, where they add it to cart themselves using "
            "the store's own button. Checkout, shipping, and payment all happen on the "
            "store's own checkout page — hand the customer to it rather than promising "
            "delivery options. Order lookups need a credential grant this deployment "
            "may not have: when the order tools return nothing, say so plainly and "
            "point the customer at their Shopify order confirmation email for status "
            "and tracking."
        ),
        product_id_patterns=(r"gid://shopify/(?:Product|ProductVariant)/\d+",),
    )