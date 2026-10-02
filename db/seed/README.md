# Seed data

Everything DynamoDB is seeded with, per stage (`sh/dynamo-seed.sh`, code `app/db/seed.py`). Tracked in git.
Now: the pricing catalog. Seeded as record kinds `services`, `subservices`, `multipliers`.

- `services.json` — services (`sk: META`) and their subservices (`sk: SUB#<id>`). Each subservice has
  `pricing.model` with only that model's fields:
  - `per_item`: `qty_prices` table by item count (extra items keep adding the last step), or `unit_price` + `min_price`
  - `flat`: `price` (times quantity)
  - `hourly`: `rate`, `min_hours` (quantity = hours)
  - `per_unit`: `unit`, `rate`, `min` (quantity = units, e.g. sq ft)
  - `option_groups`: per-subservice multipliers (e.g. with/without instructions), each with a `default`
  - `market`: range for the same job, with source and date checked
- `multipliers.json` — order-level multipliers, all compounding, >1 or <1:
  - `tiers` (picked by a number, e.g. distance), `manual` (the owner sets `value`), `lookup` (by key, e.g. state,
    with `default`), `add` (a dollar amount added after the multipliers, e.g. lead cost)

Suggested price = base × option multipliers × order multipliers + add-ons, rounded to the nearest $5.
Code: `app/catalog.py` (read from DynamoDB), `app/estimate.py` (calculate), `app/importers/` (write `services.json`).
