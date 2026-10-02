# What it does: Read-only view of the pricing catalog (app/catalog.py). GET /prices returns JSON, and
#   GET /prices/report the same rows as an HTML table. Filters (all optional, combined with AND; no
#   filters = everything): service, q (keywords), model, curated (true = hand-set pricing only),
#   max_price (baseline at quantity 1).
# When it runs: On request, in the Operator app.
# What calls it: app/main.py (router).
import html
import re

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from . import catalog
from .estimate import base_price

router = APIRouter()


def rows(
    service: str | None = None,
    q: str | None = None,
    model: str | None = None,
    curated: bool | None = None,
    max_price: float | None = None,
) -> list[dict]:
    words = re.findall(r"[a-z0-9]+", (q or "").lower())
    result = []
    for s in catalog.subservices():
        haystack = f"{s['id']} {s['name']} {s['service_id']}".lower()
        baseline = base_price(s["pricing"], 1)
        if service and s["service_id"] != service:
            continue
        if words and not all(w in haystack for w in words):
            continue
        if model and s["pricing"]["model"] != model:
            continue
        if curated is not None and curated == bool(s.get("imported")):
            continue
        if max_price is not None and baseline > max_price:
            continue
        result.append({
            "service": s["service_id"],
            "subservice": s["id"],
            "name": s["name"],
            "curated": not s.get("imported"),
            "summary": bool(s.get("summary")),
            "pricing": s["pricing"],
            "baseline": baseline,
            "options": {g["id"]: {o["id"]: o["mult"] for o in g["options"]} for g in s.get("option_groups", [])},
            "market": s.get("market"),
        })
    return sorted(result, key=lambda r: (r["service"], r["subservice"]))


_FILTERS = dict(
    service=Query(None, description="Service id, e.g. plumbing"),
    q=Query(None, description="Keywords, all must match, e.g. 'fan install'"),
    model=Query(None, description="per_item | flat | hourly | per_unit"),
    curated=Query(None, description="true = hand-set pricing only, false = imported only"),
    max_price=Query(None, description="Baseline price at quantity 1 at most this"),
)


@router.get("/prices")
async def prices(
    service: str | None = _FILTERS["service"],
    q: str | None = _FILTERS["q"],
    model: str | None = _FILTERS["model"],
    curated: bool | None = _FILTERS["curated"],
    max_price: float | None = _FILTERS["max_price"],
) -> dict:
    found = rows(service, q, model, curated, max_price)
    return {"count": len(found), "prices": found}


@router.get("/prices/report", response_class=HTMLResponse)
async def prices_report(
    service: str | None = _FILTERS["service"],
    q: str | None = _FILTERS["q"],
    model: str | None = _FILTERS["model"],
    curated: bool | None = _FILTERS["curated"],
    max_price: float | None = _FILTERS["max_price"],
) -> str:
    """Grouped report: service -> page (one Thumbtack cost page = one subservice group) -> rows.
    Every group opens and closes; open/close-all buttons at the top."""
    found = rows(service, q, model, curated, max_price)
    by_service: dict[str, dict[str, list[dict]]] = {}
    for r in found:
        page = (r["market"] or {}).get("source", "").split(" ")[0] or r["subservice"]
        by_service.setdefault(r["service"], {}).setdefault(page, []).append(r)

    sections = []
    for service_id, pages in by_service.items():
        page_blocks = []
        for page, page_rows in pages.items():
            # Title from the page's own headline row; else a hand-set row; else the first table row.
            head = next((r for r in page_rows if "__" not in r["subservice"] and not r["curated"]), None) or next(
                (r for r in page_rows if "__" not in r["subservice"]), page_rows[0]
            )
            title = html.escape(head["name"].split(" (")[0] if "__" in head["subservice"] else head["name"])
            body = "".join(
                "<tr>"
                f"<td>{html.escape(r['name'])}{' ★' if r['curated'] else ''}{' <span class=n>(summary)</span>' if r['summary'] else ''}</td>"
                f"<td>{_pricing_text(r['pricing'])}</td>"
                f"<td>{_market_text(r['market'])}</td>"
                f"<td>{html.escape(_options_text(r['options']))}</td>"
                "</tr>"
                for r in page_rows
            )
            link = f' · <a href="{html.escape(page)}">page</a>' if page.startswith("http") else ""
            page_blocks.append(
                f"<details class=sub><summary>{title} <span class=n>{len(page_rows)}</span>{link}</summary>"
                f"<table><thead><tr><th>Subservice</th><th>Our baseline</th><th>Market</th><th>Options</th></tr></thead>"
                f"<tbody>{body}</tbody></table></details>"
            )
        count = sum(len(v) for v in pages.values())
        sections.append(
            f"<details class=svc><summary>{html.escape(service_id.replace('_', ' ').title())} "
            f"<span class=n>{len(pages)} groups · {count} rows</span></summary>{''.join(page_blocks)}</details>"
        )

    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Price catalog</title>
<style>
 :root{{--bg:#fff;--fg:#111;--muted:#666;--line:#ddd;--head:#f4f4f4;--link:#0645ad}}
 @media (prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--muted:#999;--line:#333;--head:#1d1d1d;--link:#8ab4f8}}}}
 body{{font-family:system-ui,sans-serif;margin:16px;background:var(--bg);color:var(--fg)}}
 a{{color:var(--link)}}
 details.svc{{border:1px solid var(--line);border-radius:6px;margin:8px 0;padding:4px 10px}}
 details.svc>summary{{font-weight:600;font-size:16px;padding:6px 0;cursor:pointer}}
 details.sub{{margin:4px 0 4px 14px}}
 details.sub>summary{{padding:4px 0;cursor:pointer}}
 .n{{color:var(--muted);font-weight:400;font-size:13px}}
 table{{border-collapse:collapse;width:100%;font-size:14px;margin:4px 0 10px}}
 th,td{{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}}
 th{{background:var(--head)}}
 button{{margin-right:6px}}
</style></head><body>
<h1>Price catalog</h1>
<p>{len(by_service)} services · {len(found)} rows. ★ = hand-set pricing. Filters: ?service=, ?q=, ?model=, ?curated=, ?max_price=</p>
<p><button onclick="document.querySelectorAll('details').forEach(d=>d.open=true)">Open all</button>
<button onclick="document.querySelectorAll('details').forEach(d=>d.open=false)">Close all</button></p>
{''.join(sections)}
</body></html>"""


def _options_text(options: dict) -> str:
    return ", ".join(f"{g}: " + "/".join(f"{o} ×{m:g}" for o, m in opts.items()) for g, opts in options.items())


def _pricing_text(p: dict) -> str:
    model = p["model"]
    if model == "per_item":
        if "qty_prices" in p:
            return "per item: " + ", ".join(f"{k}→${v}" for k, v in list(p["qty_prices"].items())[:4]) + "…"
        return f"${p['unit_price']}/item, min ${p.get('min_price', 0)}"
    if model == "flat":
        return f"${p['price']} flat"
    if model == "hourly":
        return f"${p['rate']}/hr, min {p.get('min_hours', 0):g} h"
    return f"${p['rate']:g}/{p['unit']}" + (f", min ${p['min']}" if p.get("min") else "")


def _market_text(m: dict | None) -> str:
    if not m:
        return ""
    typical = f" (typ. ${m['typical']})" if m.get("typical") else ""
    unit = f" {m['unit']}" if m.get("unit") else ""
    src = html.escape(m["source"].split(" ")[0])
    return f"${m['low']}–{m['high']}{unit}{typical} · <a href=\"{src}\">source</a>, {m.get('checked', '')}"
