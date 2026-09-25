---
name: product-navigation
description: The customer wants to see something about a specific product rather than just hear about it — its colours, photos, other details — or wants to browse/pick it themselves. Also applies when YOU are about to ask them a colour/variant question and want to offer the real page as an option. Not needed for a general question you can just answer in text.
---

# Sending the customer to a product page

You can navigate the customer's own browser to a real product page with
navigate_to_product. Use it when seeing the actual page adds something a text
answer can't — not as a default action on every product you mention.

Two distinct modes — the difference is who's raising it:

## Immediate (immediate: true, the default) — they asked

Redirects right away. Use when the customer explicitly asked to see
something:

- They ask what colours/shades something comes in, or to see photos — the
  real page shows every swatch and image at once, better than a text list.
- They say something like "let me see it," "can I look at that," or want to
  pick a variant themselves rather than tell you which one.
- They're ready to browse a specific product's full detail page on their own.

## Offered (immediate: false, with a short label) — you're raising it

Renders a small clickable chip next to your message instead of redirecting
them outright — use this whenever YOU are the one bringing up something
they could look at, rather than them asking for it:

- You're about to ask a colour/variant question yourself ("Which colour
  would you like?") — pair it with a chip like label: "Check colours" so
  they can look at the real page if they want, without being redirected
  just for you asking.
- You're describing something visual (a texture, a pattern) where seeing it
  would help, but they haven't asked to see it.

Keep the label short and concrete: "Check colours," "See details," "View
photos" — not "Click here" or anything vague.

## When not to use either

- A quick fact question ("what's it made of," "is it machine washable") — just
  answer from get_product_details, no navigation needed.
- Early in a conversation before a specific product is settled — navigating
  too early interrupts the planning questions before they're answered.
- Right after you already navigated them somewhere this turn — don't chain
  navigations.

## How to do it

- The product_id must already be one search_products or get_product_details
  returned this session — resolve it first if it isn't.
- For immediate: say what you're doing in the same breath, naturally: "Here's
  the full range of shades for that one" rather than announcing a technical
  action.
- For offered: ask your question normally in text, and let the chip sit
  alongside it as an option — don't also describe the chip in words.
- Either way, the customer can add the item themselves from the product page,
  or keep talking to you and ask you to add a specific colour — both work, so
  don't assume which they'll choose.