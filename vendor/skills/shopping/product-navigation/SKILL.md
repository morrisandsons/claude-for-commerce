---
name: product-navigation
description: The customer wants to see something about a specific product rather than just hear about it — its colours, photos, other details — or wants to browse/pick it themselves. Not needed for a general question you can just answer in text.
---

# Sending the customer to a product page

You can navigate the customer's own browser to a real product page with
navigate_to_product. Use it when seeing the actual page adds something a text
answer can't — not as a default action on every product you mention.

## When to use it

- They ask what colours/shades something comes in, or to see photos — the real
  page shows every swatch and image at once, better than a text list.
- They say something like "let me see it," "can I look at that," or want to
  pick a variant themselves rather than tell you which one.
- They're ready to browse a specific product's full detail page on their own.

## When not to use it

- A quick fact question ("what's it made of," "is it machine washable") — just
  answer from get_product_details, no navigation needed.
- Early in a conversation before a specific product is settled — navigating
  too early interrupts the planning questions before they're answered.
- Right after you already navigated them somewhere this turn — don't chain
  navigations.

## How to do it

- The product_id must already be one search_products or get_product_details
  returned this session — resolve it first if it isn't.
- Say what you're doing in the same breath, naturally: "Here's the full range
  of shades for that one" rather than announcing a technical action.
- After navigating, the customer can add it themselves from the page, or keep
  talking to you and ask you to add a specific colour — both work, so don't
  assume which they'll choose.