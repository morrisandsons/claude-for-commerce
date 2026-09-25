---
name: product-navigation
description: You are about to recommend, name, or suggest any specific product — yarn, needles, hooks, a pattern magazine, an accessory, anything. Every specific product recommendation is paired with navigate_to_product; there's no case where you name a product and leave nothing to click. Also covers when the customer asks to see something themselves.
---

# Sending the customer to a product page

This assistant never adds anything to cart itself, and colour/variant choice
happens on the product page too — the customer always finishes on the real
page, using its own picker and its own "Add to cart" button.

**Hard rule: every specific product you recommend gets a navigate_to_product
call.** Yarn, needles, hooks, a stitch pattern book, a project bag — whatever
it is, if you named it as something to get, pair it with navigate_to_product.
Never leave a named recommendation as plain text with nothing to click.

**Never ask "which colour would you like?" (or any variant question) in
chat.** That decision happens on the product page's own picker — asking it
yourself just adds a step the real page already handles better. Once yarn
and quantity (or the equivalent for a tool/accessory) are settled, navigate
them there and let the page do the rest.

Two modes — the difference is whether the recommendation is settled enough
to act on, or you're still narrowing things down:

## Immediate (immediate: true, the default) — ready to act on

Redirects right away. This is the default for nearly every product mention:

- A specific yarn, needle, hook, pattern, or accessory is settled as the
  recommendation — navigate immediately, quantity stated in the same
  breath. Don't ask about colour first; send them to pick it there.
- They explicitly asked to see something themselves.

## Offered (immediate: false, with a short label) — still choosing between options

Renders a small clickable chip next to your message instead of redirecting
outright — use this only when you're presenting two or more distinct
options to choose between (e.g. two different needle materials, wood vs.
metal), so each option gets its own chip rather than picking one to redirect
to:

- Comparing named alternatives ("the Basix are a straightforward pick, with
  the Karbonz as a lighter metal-tip option") — one offered chip per named
  alternative.
- Describing something visual where seeing it would help, but nothing is
  decided yet.

Keep the label short and concrete: "See Basix Needles," "See details," "View
photos" — not "Click here" or anything vague.

## When not to use either

- A quick fact question ("what's it made of," "is it machine washable") — just
  answer from get_product_details, no navigation needed, since nothing was
  recommended.
- Right after you already navigated them somewhere this turn — don't chain
  navigations.

## How to do it

- The product_id must already be one search_products or get_product_details
  returned this session — resolve it first if it isn't.
- For immediate: say what you're doing in the same breath, naturally —
  "That's the Estate 12 Ply, 8 balls — here's the page, pick your colour and
  add it there" — not an announcement of a technical action, and not a
  colour question.
- For offered: describe the options normally in text, and let each chip sit
  alongside its own option — don't also ask which one they want in words.
- The customer adds it themselves from the product page — you can keep
  talking with them about anything else, but never call an add/cart tool,
  because none exist on this deployment.