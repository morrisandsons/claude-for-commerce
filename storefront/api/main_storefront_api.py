# SPDX-License-Identifier: Apache-2.0
"""Same shopping agent as ``main.py``, over a plain Shopify Storefront API backend
instead of UCP — works on any live store today, no Agentic Storefronts feature flag
required.

    uvicorn storefront.api.main_storefront_api:app --port 8004

Requires SHOP_DOMAIN and SHOPIFY_STOREFRONT_TOKEN (see storefront/.env). Sign in with
Shop and UCP checkout staging aren't available on this path — the cart's own
``checkoutUrl`` is the handoff instead, which needs no staging step at all.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from commerce_common.memory import InMemoryMemoryStore
from demo_common import (
    REPO_ROOT,
    CartAddRequest,
    MemorySeeder,
    build_storefront_host,
    load_demo_env,
)
from shopping_agent_runtime import ShoppingAgent

from .agent_config import build_shopping_config
from .brand import BrandSource
from .catalog_warmup import warm_catalog
from .navigate_tool import NAVIGATE_TO_PRODUCT
from .rate_limit import ChatRateLimitMiddleware
from .storefront_graphql_backend import (
    ShopifyStorefrontAPIBackend,
    cart_gid,
    shop_domain_from_env,
)

logger = logging.getLogger(__name__)

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = EXAMPLE_ROOT / "data"

load_demo_env(EXAMPLE_ROOT)

store_name = shop_domain_from_env()
brand_source = BrandSource(store_name)
backend = ShopifyStorefrontAPIBackend(store_name, store_name=store_name)
agent = ShoppingAgent(
    backend=backend,
    skills_dir=REPO_ROOT / "vendor" / "skills" / "shopping",
    config=build_shopping_config(store_name),
    memory_store=InMemoryMemoryStore(),
    extra_presentation_tools=[NAVIGATE_TO_PRODUCT],
)


async def cart_extras(record) -> dict:
    """The cart's own checkoutUrl is the handoff link on this path — no UCP staging
    step needed, unlike main.py's cart_extras."""
    return {
        "checkout_url": await backend.checkout_url_for(record.session_id),
        "cart_id": backend.cart_id_for(record.session_id),
    }


host = build_storefront_host(
    title="Shopify Storefront API demo",
    example_root=EXAMPLE_ROOT,
    backend=backend,
    agent=agent,
    memory_seeder=MemorySeeder(DATA_DIR / "memory-seed.json"),
    cart_extras=cart_extras,
)
app = host.app
app.add_middleware(ChatRateLimitMiddleware)

# Same background catalog warm-up as main.py.
_host_lifespan = app.router.lifespan_context
_warmup_task: asyncio.Task | None = None


@asynccontextmanager
async def _lifespan_with_warmup(app_) -> AsyncIterator[None]:
    global _warmup_task
    async with _host_lifespan(app_):
        _warmup_task = asyncio.create_task(warm_catalog(backend, store_name))
        yield


app.router.lifespan_context = _lifespan_with_warmup


@app.post("/api/cart/add")
async def cart_add(request: CartAddRequest, record: host.CurrentSession) -> dict:
    return await host.direct_add(
        record,
        request,
        note="Customer tapped the add-to-cart button on {title} ({product_id}), quantity {quantity}.",
    )


@app.post("/api/cart/attach")
async def cart_attach(request: dict, record: host.CurrentSession) -> dict:
    """Bind the session to a cart the storefront already holds (its ``cart`` cookie
    value, or the full gid)."""
    cart_id = request.get("cart_id")
    if not cart_id or await backend.attach_cart(record.session_id, cart_gid(cart_id)) is None:
        raise HTTPException(status_code=404, detail="The shop doesn't know that cart")
    return await host.cart_payload(record)


@app.get("/api/products/{product_id:path}/url")
async def product_page_url(product_id: str, bare: bool = False) -> dict:
    """A real, relative product page URL for a product or variant id — used by the
    widget to attach a "See details" chip to every product the agent recommends via
    present_products, deterministically, without depending on the model remembering
    to call navigate_to_product separately every time.

    bare=true always returns the plain product page (no ?variant=...), even for a
    variant id — the widget uses this for present_products' auto-chips, so several
    variant-level picks of one product de-duplicate to a single chip rather than
    one per colour."""
    url = await backend.get_product_url(product_id, include_variant=not bare)
    if not url:
        raise HTTPException(status_code=404, detail="No page URL available for that product yet")
    title = None
    details = backend.products.get(product_id)
    if details:
        title = details.title
    else:
        for product in backend.products.values():
            match = next((v for v in product.variants if v.product_id == product_id), None)
            if match:
                # bare=True means the link points at the general product page,
                # not this specific colour — use the parent's plain title so
                # the chip's label doesn't imply a colour it isn't linking to.
                title = product.title if bare else match.title
                break
    return {"url": url, "title": title}


@app.get("/api/brand")
async def brand(request=None) -> dict:
    """Same tokenless brand read as main.py."""
    return await brand_source.brand(None)