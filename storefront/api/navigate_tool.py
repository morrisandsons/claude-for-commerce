# SPDX-License-Identifier: Apache-2.0
"""A custom presentation tool, added via ShoppingAgent's `extra_presentation_tools`
extension point (see commerce_common.presentation.PresentationExtension). Lets the
agent navigate the customer's browser to a real product page — e.g. when asked to see
a product's colours or photos — rather than only describing it in text.

The widget (assets/craft-assistant.js) is what actually performs the navigation: it
watches for a `ui` event with component == "navigate" and does
`window.location.href = payload.url`. The chat survives that navigation via the
widget's own session-persistence (localStorage), the same as it survives a manual
link click or a plain page refresh.
"""

from __future__ import annotations

from typing import Any

from commerce_common.presentation import EnrichmentContext, PresentationExtension, PresentationRefused
from pydantic import BaseModel, Field
from shopping_agent.gates import PROVENANCE_GATE


class NavigateToProductPayload(BaseModel):
    product_id: str = Field(
        description="The product or variant id to navigate to — must be one already "
        "returned by search_products or get_product_details this session."
    )
    reason: str | None = Field(
        default=None,
        description="Optional short note on why you're sending them there, e.g. "
        "'so you can see all the colourways'.",
    )


async def _enrich_navigate(payload: NavigateToProductPayload, context: EnrichmentContext) -> dict[str, Any]:
    if payload.product_id not in context.state.seen_products:
        raise PresentationRefused(
            f"product_id {payload.product_id} was not returned by catalog tools in "
            "this session. Resolve it first with get_product_details or a search, "
            "then navigate using that id.",
            PROVENANCE_GATE,
        )
    url = context.backend.get_product_url(payload.product_id)
    if not url:
        raise PresentationRefused(
            f"No page URL is available yet for product_id {payload.product_id}."
        )
    return {"product_id": payload.product_id, "url": url, "reason": payload.reason}


NAVIGATE_TO_PRODUCT = PresentationExtension(
    name="navigate_to_product",
    component="navigate",
    payload_model=NavigateToProductPayload,
    description=(
        "Navigate the customer's own browser to a specific product's page. Use this "
        "when they ask to see a product's colours, photos, or other details, or "
        "want to browse/pick it themselves — not for every product mention, just "
        "when seeing the real page adds something a text description can't. Only "
        "call this with a product_id already returned by search_products or "
        "get_product_details this session."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "The product or variant id to navigate to, from a "
                "prior search_products or get_product_details result.",
            },
            "reason": {
                "type": "string",
                "description": "Optional short note on why you're navigating them "
                "there.",
            },
        },
        "required": ["product_id"],
    },
    enrich=_enrich_navigate,
)