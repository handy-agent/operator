# What it does: Imports Thumbtack's public cost guides into the pricing catalog. Reads the index
#   (https://www.thumbtack.com/prices), takes every page under the chosen top category (default
#   "Home Improvement"), and reads each page's "national average ... ranges from around $X-$Y, and
#   most people pay around $Z" line. Each index subsection (e.g. "Plumbing") becomes a service, each
#   page a subservice with a baseline price and its market range. Three page formats are read:
#   "ranges from around $X-$Y, and most people pay around $Z" / "is between $X and $Y ... Most people
#   pay around $Z" (flat price = typical), and "National average hourly|fixed price, Most common low
#   price $X, high $Y" (hourly rate or flat price = midpoint). Price tables on a page (e.g. the
#   handyman page's "by project type" / "price list" / "by scope of work") add one subservice per row.
#   Hand-curated subservices (no "imported" flag) keep their pricing; only their market range is
#   refreshed when their source is the same page.
# When it runs: By hand when prices should be refreshed. Polite: one request per second.
# What calls it: sh/import-thumbtack-prices.sh.
import html as html_lib
import json
import re
import sys
import time
from datetime import date

import httpx

from ..db.seed import SEED_DIR

INDEX_URL = "https://www.thumbtack.com/prices"
HEADERS = {"User-Agent": "Mozilla/5.0 (Handy Agent price research)"}
TOP_CATEGORIES = ["Business", "Events", "Home Improvement", "Lessons", "Pets & Wellness"]
_RANGE = re.compile(
    r"national average cost[^$]{0,160}?\$([\d,]+)\s*-\s*\$([\d,]+)[^$]{0,80}?most people pay around \$([\d,]+)",
    re.IGNORECASE,
)
_BETWEEN = re.compile(
    r"national average cost[^$]{0,160}?between \$([\d,]+) and \$([\d,]+)[^$]{0,300}?most people pay around \$([\d,]+)",
    re.IGNORECASE,
)
_LOW_HIGH = re.compile(
    r"national average (hourly|fixed) price\s*most common low price:\s*\$\s*([\d,]+)\s*most common high price:\s*\$\s*([\d,]+)",
    re.IGNORECASE,
)
_TABLE = re.compile(r"<table.*?</table>", re.DOTALL)
_HEADING = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", re.DOTALL)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL)
# A price at the start of a cell: "$9", "$9-$21", "$200 to $3,000", "$55+", optionally followed by a unit
# ("/hour", "per sq. ft.") and/or a note (", depending on the type of wood", "(full bath)").
_CELL_PRICE = re.compile(
    r"^\$\s?([\d,]+(?:\.\d+)?)\+?(?:\s*(?:-|–|to)\s*\$?\s?([\d,]+(?:\.\d+)?))?(.*)$",
    re.IGNORECASE,
)
_HOURLY = re.compile(r"^\s*(?:/\s*(?:hour|hr)|per (?:hour|hr))\b", re.IGNORECASE)
_PER_UNIT = re.compile(r"^\s*(?:/|per)\s*([a-z][a-z .]*?)(?=[,(;]|$)", re.IGNORECASE)
# Table rows that restate the page's overall range ("Low-end cost", "National average rate"...) rather
# than naming a job. Kept in the catalog for reference, but never offered to the agent as a job.
SUMMARY_LABEL = re.compile(
    r"^(national average|average|low[- ]end|high[- ]end|most common|typical|median|minimum|maximum)\b", re.IGNORECASE
)
# Whether the page's prices include parts/materials — pages say it differently, so keep the sentence.
_MATERIALS_IN = re.compile(r"[^.]{0,200}\binclud(?:es|ing) (?:both )?(?:labor and materials|materials and labor|materials|parts)\b[^.]{0,120}\.", re.I)
_MATERIALS_OUT = re.compile(
    r"[^.]{0,200}\b(?:does not include|doesn't include|not including|excluding|excludes|labor only|plus the cost of)\b[^.]{0,160}\.", re.I
)
_SECTION = re.compile(r"<div[^>]*>([^<]+)</div><ul[^>]*>(.*?)</ul>", re.DOTALL)
_LINK = re.compile(r'<a href="(https://www\.thumbtack\.com/p/[^"]+)"[^>]*>([^<]+)</a>')


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def subservice_id(page_url: str) -> str:
    name = page_url.rstrip("/").rsplit("/", 1)[-1]
    name = re.sub(r"^(cost-to-|cost-of-|how-much-does-it-cost-to-|how-much-to-|how-much-)", "", name)
    name = re.sub(r"(-cost|-costs|-prices|-price|-pricing)$", "", name)
    return slug(name)


def index_sections(html: str, top_category: str) -> dict[str, list[tuple[str, str]]]:
    start = html.find(f">{top_category}<")
    following = [html.find(f">{c}<", start + 1) for c in TOP_CATEGORIES if c != top_category]
    end = min([i for i in following if i > start], default=len(html))
    return {
        html_lib.unescape(name.strip()): [(url, html_lib.unescape(title)) for url, title in _LINK.findall(links)]
        for name, links in _SECTION.findall(html[start:end])
        if _LINK.search(links)
    }


def _num(s: str) -> float:
    value = float(s.replace(",", ""))
    return int(value) if value.is_integer() else value


def parse_page(html: str) -> tuple[dict, dict] | None:
    """Returns (market, pricing), or None if no known price format is on the page."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    if match := _RANGE.search(text) or _BETWEEN.search(text):
        low, high, typical = (_num(g) for g in match.groups())
        return {"low": low, "high": high, "typical": typical}, {"model": "flat", "price": typical}
    if match := _LOW_HIGH.search(text):
        kind, low, high = match.group(1).lower(), _num(match.group(2)), _num(match.group(3))
        mid = int(5 * round((low + high) / 2 / 5))
        if kind == "hourly":
            return {"low": low, "high": high, "unit": "per hour"}, {"model": "hourly", "rate": mid, "min_hours": 1}
        return {"low": low, "high": high}, {"model": "flat", "price": mid}
    return None


def _plain(fragment: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _row_entries(cells: list[str]) -> list[dict]:
    """Every price cell after the first column becomes one entry, labeled by the row's other cells."""
    words = [c for c in cells[1:] if not _CELL_PRICE.match(c)]
    entries = []
    for cell in cells[1:]:
        if not (price := _CELL_PRICE.match(cell)):
            continue
        low = _num(price.group(1))
        high = _num(price.group(2)) if price.group(2) else low
        rest = price.group(3)
        if _HOURLY.match(rest):
            market, pricing = {"low": low, "high": high, "unit": "per hour"}, {"model": "hourly", "rate": int(5 * round((low + high) / 2 / 5)), "min_hours": 1}
            rest = _HOURLY.sub("", rest)
        elif unit_match := _PER_UNIT.match(rest):
            unit = unit_match.group(1).strip().rstrip(".").lower()
            market = {"low": low, "high": high, "unit": f"per {unit}"}
            pricing = {"model": "per_unit", "unit": unit, "rate": round((low + high) / 2, 2), "min": 0}
            rest = rest[unit_match.end():]
        else:
            market, pricing = {"low": low, "high": high}, {"model": "flat", "price": int(5 * round((low + high) / 2 / 5))}
        note = rest.strip(" ,;.()")
        label = " — ".join([cells[0], *words]) + (f" ({note})" if note else "")
        entries.append({"label": label[:160], "market": market, "pricing": pricing})
    return entries


def parse_tables(html: str) -> list[dict]:
    """Price-table rows: [{"table", "label", "market", "pricing", "row"}] ("row" identifies the table row)."""
    found = []
    for t_index, table in enumerate(_TABLE.finditer(html)):
        headings = _HEADING.findall(html[: table.start()])
        table_title = _plain(headings[-1]) if headings else ""
        for r_index, row in enumerate(_ROW.findall(table.group(0))):
            cells = [_plain(c) for c in _CELL.findall(row)]
            if len(cells) < 2:
                continue
            for entry in _row_entries(cells):
                found.append({"table": table_title, "row": (t_index, r_index), **entry})
    return found


def parse_materials(html: str) -> dict:
    """The headline price sentence wins ("...between $X and $Y, including labor and materials");
    otherwise an exclusion of the item/parts ("does not include the cost of the fan"), ignoring ones
    about fees; otherwise any inclusion sentence."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

    def found(status: str, match: re.Match) -> dict:
        return {"materials": status, "materials_quote": html_lib.unescape(match.group(0).strip())[:300]}

    included = list(_MATERIALS_IN.finditer(text))
    for match in included:
        if "national average" in match.group(0).lower():
            return found("included", match)
    for match in _MATERIALS_OUT.finditer(text):
        if not re.search(r"\bfees?\b", match.group(0), re.IGNORECASE):
            return found("excluded", match)
    return found("included", included[0]) if included else {"materials": "unknown"}


def count_price_rows(html: str) -> int:
    """Independent completeness check: every table row with a "$" anywhere, however it's formatted."""
    return sum(
        1 for table in _TABLE.finditer(html) for row in _ROW.findall(table.group(0)) if "$" in _plain(row)
    )


def merge(
    items: list[dict], section: str, page_url: str, title: str, market: dict, pricing: dict, sub_id: str | None = None
) -> str:
    """Updates items in place. Returns "curated", "updated" or "added"."""
    # Only the page's headline range refreshes a hand-curated subservice — never a table row.
    for item in items if sub_id is None else []:
        if item.get("market", {}).get("source") == page_url and not item.get("imported"):
            item["market"] = {**item["market"], **market}
            return "curated"
    service_pk = f"SERVICE#{slug(section)}"
    if not any(i["pk"] == service_pk and i["sk"] == "META" for i in items):
        items.append({"pk": service_pk, "sk": "META", "name": section, "platforms": {"thumbtack": section}, "active": True})
    sk = f"SUB#{sub_id or subservice_id(page_url)}"
    existing = next((i for i in items if i["pk"] == service_pk and i["sk"] == sk), None)
    record = {
        "pk": service_pk, "sk": sk,
        "name": re.sub(r"\s*(cost|costs|prices|price|pricing)$", "", title, flags=re.IGNORECASE).strip(),
        "platforms": {"thumbtack": section},
        "pricing": pricing,
        "option_groups": [],
        "market": market,
        "imported": "thumbtack",
    }
    if sub_id is not None and SUMMARY_LABEL.match(title):
        record["summary"] = True
    if existing:
        existing.update(record)
        return "updated"
    items.append(record)
    return "added"


def main(top_category: str = "Home Improvement") -> None:
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        sections = index_sections(client.get(INDEX_URL).text, top_category)
        path = SEED_DIR / "services.json"
        items = json.loads(path.read_text())
        counts = {"curated": 0, "updated": 0, "added": 0}
        skipped = []
        coverage = []  # (page, rows with a price on the page, rows imported)
        for section, links in sections.items():
            for page_url, title in links:
                time.sleep(1)
                try:
                    page_html = client.get(page_url).text
                except httpx.HTTPError as e:
                    skipped.append(f"{page_url} ({e.__class__.__name__})")
                    continue
                checked = date.today().isoformat()
                materials = parse_materials(page_html)
                parsed = parse_page(page_html)
                if parsed is not None:
                    market, pricing = parsed
                    counts[merge(items, section, page_url, title, {**market, "source": page_url, "checked": checked, **materials}, pricing)] += 1
                rows = parse_tables(page_html)
                headline_from_table = parsed is None and next(
                    (r for r in rows if r["label"].lower().startswith("national average")), None
                )
                for row in rows:
                    sub_id = f"{subservice_id(page_url)}__{slug(row['label'])[:80]}"
                    name = f"{row['label']} ({row['table']})" if row["table"] else row["label"]
                    market = {**row["market"], "source": page_url, "checked": checked, **materials}
                    if row is headline_from_table:
                        # No headline sentence on this page: its table's national-average row is the page's price.
                        counts[merge(items, section, page_url, title, market, row["pricing"])] += 1
                        continue
                    counts[merge(items, section, page_url, name, market, row["pricing"], sub_id)] += 1
                on_page = count_price_rows(page_html)
                rows_read = len({r["row"] for r in rows})
                if rows_read < on_page:
                    coverage.append((page_url, on_page, rows_read))
                if parsed is None and not rows:
                    skipped.append(f"{page_url} (no price line or table)")
            path.write_text(json.dumps(items, indent=2) + "\n")  # save after each section
            print(f"{section}: {len(links)} pages", flush=True)
    print(f"Done. {counts}. Skipped {len(skipped)}:")
    for line in skipped:
        print("  ", line)
    missed = sum(on_page - got for _, on_page, got in coverage)
    print(f"Coverage: {len(coverage)} pages have table rows with a price that weren't imported ({missed} rows):")
    for page_url, on_page, got in coverage:
        print(f"   {page_url}: {got}/{on_page} rows")


if __name__ == "__main__":
    main(*sys.argv[1:2])
