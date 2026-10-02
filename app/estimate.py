# What it does: Calculates a suggested price for the owner from the pricing catalog (app/catalog.py):
#   base price by the subservice's pricing model × its option multipliers × every order multiplier
#   (compounding), plus add-ons (e.g. lead cost), rounded to the nearest $5 (decided 2026-09-23).
#   It's a baseline — the owner checks the photos/link for the real job size before confirming.
# When it runs: When the agent calls propose_estimate for a lead.
# What calls it: app/tools.py.
from dataclasses import dataclass, field

from . import catalog


@dataclass
class EstimateInput:
    subservice_id: str
    quantity: float = 1  # items, hours, or units depending on the pricing model
    options: dict[str, str] = field(default_factory=dict)
    state: str | None = None
    distance_miles: float | None = None
    lead_cost: float | None = None


@dataclass
class Applied:
    name: str
    value: float
    kind: str  # "mult" | "add"
    why: str = ""


@dataclass
class EstimateResult:
    subservice_id: str
    base: float
    applied: list[Applied]
    suggested: int
    market: dict | None
    unknown: list[str]
    confidence: int = 10
    confidence_why: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"base ${self.base:g}"]
        for a in self.applied:
            parts.append(f"{a.name} +${a.value:g}" if a.kind == "add" else f"{a.name} ×{a.value:g}")
        line = f"Suggested ${self.suggested} ({', '.join(parts)})"
        if self.market:
            unit = f" {self.market['unit']}" if self.market.get("unit") else ""
            line += f". Market ${self.market['low']}-{self.market['high']}{unit} ({self.market['source']})"
        if self.market and self.market.get("materials") in ("included", "excluded"):
            line += f". Market price {'includes' if self.market['materials'] == 'included' else 'does NOT include'} parts/materials"
        elif self.market:
            line += ". Unknown if market price includes parts/materials"
        if self.unknown:
            line += f". Not included (unknown): {', '.join(self.unknown)}"
        line += f". Confidence {self.confidence}/10" + (f" ({'; '.join(self.confidence_why)})" if self.confidence_why else "")
        return line


def base_price(pricing: dict, quantity: float) -> float:
    model = pricing["model"]
    if model == "per_item":
        if "qty_prices" in pricing:
            return _from_qty_table(pricing["qty_prices"], int(max(1, round(quantity))))
        return max(pricing["unit_price"] * quantity, pricing.get("min_price", 0))
    if model == "flat":
        return pricing["price"] * max(1, quantity)
    if model == "hourly":
        return pricing["rate"] * max(quantity, pricing.get("min_hours", 0))
    if model == "per_unit":
        return max(pricing["rate"] * quantity, pricing.get("min", 0))
    raise ValueError(f"Unknown pricing model {model!r}")


def _from_qty_table(table: dict[str, float], quantity: int) -> float:
    counts = sorted(int(k) for k in table)
    if quantity in counts:
        return table[str(quantity)]
    last = counts[-1]
    step = table[str(last)] - table[str(counts[-2])] if len(counts) > 1 else table[str(last)]
    return table[str(last)] + step * (quantity - last)


def estimate(inp: EstimateInput) -> EstimateResult:
    sub = catalog.subservice(inp.subservice_id)
    if sub is None:
        raise ValueError(f"Unknown subservice {inp.subservice_id!r}")

    base = base_price(sub["pricing"], inp.quantity)
    applied: list[Applied] = []
    unknown: list[str] = []

    for group in sub.get("option_groups", []):
        chosen = inp.options.get(group["id"], group["default"])
        option = next((o for o in group["options"] if o["id"] == chosen), None)
        if option is None:
            unknown.append(f"{group['id']}={chosen}")
            option = next(o for o in group["options"] if o["id"] == group["default"])
        if option["mult"] != 1:
            applied.append(Applied(f"{group['id']}={option['id']}", option["mult"], "mult"))

    context = {"state": inp.state, "distance_miles": inp.distance_miles, "lead_cost": inp.lead_cost}
    for mult in catalog.multipliers():
        item = _apply_order_multiplier(mult, context)
        if item is None:
            unknown.append(mult["id"])
        elif item.kind == "add" or item.value != 1:
            applied.append(item)

    total = base
    for a in applied:
        if a.kind == "mult":
            total *= a.value
    total += sum(a.value for a in applied if a.kind == "add")

    confidence, why = _confidence(sub, unknown)
    return EstimateResult(
        subservice_id=inp.subservice_id,
        base=base,
        applied=applied,
        suggested=int(5 * round(total / 5)),
        market=sub.get("market"),
        unknown=unknown,
        confidence=confidence,
        confidence_why=why,
    )


def _confidence(sub: dict, unknown: list[str]) -> tuple[int, list[str]]:
    """10 = sure. Loses points for each thing that makes the baseline shakier."""
    score, why = 10, []
    if sub.get("imported"):
        score -= 2
        why.append("price not hand-set, taken from market data")
    market = sub.get("market") or {}
    if market.get("low") and market.get("high", 0) / market["low"] > 3:
        score -= 2
        why.append(f"very wide market range ${market['low']}-{market['high']}")
    elif market.get("low") and market.get("high", 0) / market["low"] > 2:
        score -= 1
        why.append(f"wide market range ${market['low']}-{market['high']}")
    if market.get("materials", "unknown") == "unknown":
        score -= 1
        why.append("unknown if parts/materials are included")
    for item in unknown:
        score -= 1
        why.append(f"{item} unknown")
    return max(1, score), why


def _apply_order_multiplier(mult: dict, context: dict) -> Applied | None:
    """None means the input it needs is unknown (so it's left out and reported)."""
    kind = mult["kind"]
    if kind == "manual":
        return Applied(mult["id"], mult["value"], "mult")
    if kind == "tiers":
        value = context.get(mult["key"])
        if value is None:
            return None
        tier = next(t for t in mult["tiers"] if t["max"] is None or value <= t["max"])
        return Applied(mult["id"], tier["mult"], "mult", f"{value:g}")
    if kind == "lookup":
        key = context.get(mult["key"])
        return Applied(mult["id"], mult["values"].get(key, mult["default"]) if key else mult["default"], "mult", key or "")
    if kind == "add":
        value = context.get(mult["key"])
        return Applied(mult["id"], value if value is not None else mult["default"], "add")
    raise ValueError(f"Unknown multiplier kind {kind!r}")
