# SPDX-License-Identifier: Apache-2.0
"""A custom presentation tool, added via ShoppingAgent's `extra_presentation_tools`
extension point (see commerce_common.presentation.PresentationExtension). Lets the
agent send the customer's browser to a real product page — e.g. when asked to see a
product's colours or photos — rather than only describing it in text.

Two modes, both handled by the widget (assets/craft-assistant.js) from the same `ui`
event with component == "navigate":
  - immediate=True (default): the widget redirects right away — for when the
    customer explicitly asked to see something.
  - immediate=False: the widget instead renders a small clickable chip (labelled
    with `label`) alongside the agent's text — for when the AGENT is the one
    raising it (e.g. asking a colour question itself) and shouldn't redirect the
    customer without them choosing to. Clicking the chip navigates then, using the
    same URL resolved here.

Either way, the chat survives the eventual navigation via the widget's own
session-persistence (localStorage), the same as it survives a manual link click or a
plain page refresh.
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
    immediate: bool = Field(
        default=True,
        description="True: redirect the customer's browser there right now (they "
        "asked to see it). False: just offer a clickable chip instead — use this "
        "when you're the one raising it, e.g. asking them a colour question "
        "yourself, so you're not redirecting them without them choosing to.",
    )
    label: str | None = Field(
        default=None,
        description="Short label for the clickable chip when immediate is False, "
        "e.g. 'Check colours' or 'See details'. Ignored when immediate is True.",
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
    return {
        "product_id": payload.product_id,
        "url": url,
        "reason": payload.reason,
        "immediate": payload.immediate,
        "label": payload.label or "View product",
    }


NAVIGATE_TO_PRODUCT = PresentationExtension(
    name="navigate_to_product",
    component="navigate",
    payload_model=NavigateToProductPayload,
    description=(
        "Send the customer's browser to a specific product's page, or offer a "
        "clickable chip to do so. Use immediate=true when they explicitly asked to "
        "see a product's colours, photos, or details. Use immediate=false with a "
        "short label (e.g. 'Check colours') when YOU are the one raising it — for "
        "instance, when you're about to ask them a colour/variant question "
        "yourself — so they get the option to look at the real page without being "
        "redirected without choosing to. Only call this with a product_id already "
        "returned by search_products or get_product_details this session."
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
            "immediate": {
                "type": "boolean",
                "description": "True (default): redirect right now. False: offer a "
                "clickable chip instead of redirecting immediately.",
            },
            "label": {
                "type": "string",
                "description": "Short label for the chip when immediate is false, "
                "e.g. 'Check colours'.",
            },
        },
        "required": ["product_id"],
    },
    enrich=_enrich_navigate,
)