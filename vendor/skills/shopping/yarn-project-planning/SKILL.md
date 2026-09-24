---
name: yarn-project-planning
description: The customer is working out what yarn or tools they need for a knitting or crochet project — a garment, blanket, or accessory — whether or not they already have a pattern. Not needed when they've already named a specific product and quantity and just want to buy it.
---

# Planning a yarn project

Get the project settled before recommending anything. A yardage guess without
these facts is a guess the customer will pay for in a second trip to the shop.

## Frame it

- Four facts shape a recommendation: knit or crochet, what they're making, the
  ply/weight (from a pattern if they have one), and — for anything fit
  depends on, like a jumper or cardigan — gauge/tension. Ask for whichever of
  these the request and conversation don't already give you, one or two
  questions at a time, not a formal intake list.
- Skip the gauge question for projects where fit doesn't matter: scarves,
  blankets, simple accessories.
- If they have a pattern, ask for its stated ply/weight and metres or grams
  required rather than estimating from the project type alone.

## Search and recommend

- Always call search_catalog before stating price, stock, or ply — never
  recommend from memory.
- If the specific yarn or colourway is unavailable, search within the same
  product family first (same ply, similar fibre content) before widening the
  search. Only offer a substitute close enough in ply and fibre that gauge
  won't be meaningfully affected.
- If the closest available substitute differs in fibre content (wool vs.
  wool-blend, natural vs. synthetic), say so explicitly rather than letting
  the customer discover it after the project is underway.
- Size the quantity from the facts gathered above and state the number you
  sized to, so the customer can correct it if a detail was off.

## Show it

- Present the recommendation with the yarn, ply, quantity, and why — one
  short block, not a wall of caveats.
- If you're recommending a substitute, name what changed (fibre, drape, care)
  in the same turn, not as an afterthought.

## Adding to cart

- Never call add_to_cart from an inferred suggestion. Restate exactly what
  you're about to add — product, colour, and quantity — and wait for a clear
  yes before adding it. "Should I add 6 balls of the Estate 8 Ply in Jasmine?"
  not a silent add after recommending it.
- A direct, specific request ("add 6 balls of Jasmine") is already
  confirmation on its own — don't ask again for something they just told you
  plainly.
- If any of product, colour, or quantity is still ambiguous, resolve that
  first — an add with a guessed colour is not a confirmed add.
- To change their mind, use update_cart_item (change quantity) or
  remove_from_cart (take it out) rather than adding a second line for the
  same product — check get_cart first if you're not sure what's already
  there.