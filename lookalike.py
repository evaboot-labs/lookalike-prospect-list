#!/usr/bin/env python3
"""Lookalike prospect list: from your best customers to a clean list of people at companies like them.

  python3 lookalike.py profile SEEDS.md               -> what your customers share, and the Sales Navigator filters
  python3 lookalike.py url "<people search url>" SEEDS.md  -> the search with industry, size and seed exclusions added
  python3 lookalike.py clean data/export.json SEEDS.md [--exclude data/exclude.txt] > data/list.csv

Standard library only. The Evaboot work happens in your AI agent through the Evaboot MCP server.
"""
import csv
import json
import re
import sys
from collections import Counter
from urllib.parse import quote

# Sales Navigator company headcount codes.
HEADCOUNT = {
    "1 to 10": "B", "11 to 50": "C", "51 to 200": "D", "201 to 500": "E",
    "501 to 1000": "F", "1001 to 5000": "G", "5001 to 10000": "H", "10001+": "I",
}
# LinkedIn industry ids for the industries seen most often. Add yours: the id is in
# the INDUSTRY filter of a Sales Navigator URL after you pick that industry by hand.
INDUSTRY = {
    "Software Development": 4,
    "Technology, Information and Internet": 6,
    "Financial Services": 43,
    "IT Services and IT Consulting": 96,
    "Business Consulting and Services": 11,
    "Advertising Services": 80,
}


def read_seeds(path):
    """Seeds are the table in SEEDS.md: | Company | LinkedIn id | Domain | Industry | Employees | Location |"""
    rows = []
    for line in open(path, encoding="utf-8"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[0] in ("Company", "") or set(cells[0]) <= set("-: "):
            continue
        name, lid, domain, industry, employees, location = cells[:6]
        rows.append({
            "name": name, "id": re.sub(r"\D", "", lid), "domain": domain.lower(),
            "industry": industry, "employees": employees, "location": location,
        })
    if len(rows) < 2:
        sys.exit(f"{path}: fill the seed table with at least 2 customers (3 to 5 is best).")
    return rows


def region(location):
    """'Paris, Île-de-France, France' -> 'Île-de-France, France' (region and country)."""
    parts = [p.strip() for p in location.split(",")]
    return ", ".join(parts[-2:]) if len(parts) >= 2 else location


def profile(seeds):
    n = len(seeds)
    industries = Counter(s["industry"] for s in seeds)
    sizes = Counter(s["employees"] for s in seeds)
    regions = Counter(region(s["location"]) for s in seeds)
    keep = lambda c: [k for k, v in c.most_common() if v >= 1]
    return {
        "seeds": n,
        "industries": keep(industries),
        "employees": sorted(keep(sizes), key=lambda s: "BCDEFGHI".index(HEADCOUNT.get(s, "I"))),
        "regions": keep(regions),
        "industry_ids": [INDUSTRY[i] for i in keep(industries) if i in INDUSTRY],
        "unknown_industries": [i for i in keep(industries) if i not in INDUSTRY],
        "headcount_codes": [HEADCOUNT[s] for s in keep(sizes) if s in HEADCOUNT],
        "exclude_company_ids": [s["id"] for s in seeds if s["id"]],
    }


def cmd_profile(seeds_path):
    seeds = read_seeds(seeds_path)
    p = profile(seeds)
    print(f"{p['seeds']} customers. What they share:")
    for label, key in (("Industry", "industries"), ("Employees", "employees"), ("Region", "regions")):
        counts = Counter(
            s["industry"] if key == "industries" else s["employees"] if key == "employees" else region(s["location"])
            for s in seeds)
        print(f"- {label}: " + ", ".join(f"{k} ({counts[k]}/{p['seeds']})" for k in p[key]))
    print(f"\nSales Navigator filters: INDUSTRY {p['industry_ids']}, COMPANY_HEADCOUNT {p['headcount_codes']}, "
          f"exclude {len(p['exclude_company_ids'])} seed companies")
    if p["unknown_industries"]:
        print(f"Industry id unknown, add it to INDUSTRY in lookalike.py: {p['unknown_industries']}")
    print(f"\nPeople part for build_sn_search_from_prompt: <roles you sell to> based in {', '.join(p['regions'])}.")


def add_filters(url, p):
    """Add INDUSTRY, COMPANY_HEADCOUNT and the seed exclusions to a Sales Navigator people search URL."""
    if "filters%3AList(" not in url:
        sys.exit("Expected a Sales Navigator people search URL with filters (from build_sn_search_from_prompt).")
    parts = []
    if p["industry_ids"]:
        vals = "%2C".join(f"(id%3A{i}%2CselectionType%3AINCLUDED)" for i in p["industry_ids"])
        parts.append(f"(type%3AINDUSTRY%2Cvalues%3AList({vals}))")
    if p["headcount_codes"]:
        vals = "%2C".join(f"(id%3A{c}%2CselectionType%3AINCLUDED)" for c in p["headcount_codes"])
        parts.append(f"(type%3ACOMPANY_HEADCOUNT%2Cvalues%3AList({vals}))")
    # The people search filters on where the person lives. Your customers' region is where the
    # company is based: add the same regions as a company headquarters filter.
    regions = re.search(r"type%3AREGION%2Cvalues%3AList\(((?:\(id%3A\d+%2CselectionType%3AINCLUDED\)(?:%2C)?)+)\)", url)
    if regions and "COMPANY_HEADQUARTERS" not in url:
        parts.append(f"(type%3ACOMPANY_HEADQUARTERS%2Cvalues%3AList({regions.group(1)}))")
    if p["exclude_company_ids"]:
        vals = "%2C".join(
            f"(id%3A{quote(quote(f'urn:li:organization:{i}', safe=''), safe='')}%2CselectionType%3AEXCLUDED)"
            for i in p["exclude_company_ids"])
        parts.append(f"(type%3ACURRENT_COMPANY%2Cvalues%3AList({vals}))")
    if not parts:
        sys.exit("No lookalike filter to add: the seeds have no known industry, size or LinkedIn id.")
    return url.replace("filters%3AList(", "filters%3AList(" + "%2C".join(parts) + "%2C", 1)


def cmd_url(url, seeds_path):
    print(add_filters(url, profile(read_seeds(seeds_path))))


def domain(value):
    value = (value or "").lower().strip()
    value = re.sub(r"^https?://", "", value)
    return value.split("/")[0].removeprefix("www.")


def cmd_clean(export_path, seeds_path, exclude_path=None):
    seeds = read_seeds(seeds_path)
    data = json.load(open(export_path, encoding="utf-8"))
    while isinstance(data, dict) and "prospects" not in data:  # get_export JSON nests the result
        data = data.get("structuredContent") or data.get("result") or {}
    leads = data.get("prospects", []) if isinstance(data, dict) else data
    if not isinstance(leads, list) or not leads:
        sys.exit(f"{export_path}: no prospects found.")
    blocked = {s["domain"] for s in seeds if s["domain"]} | {s["name"].lower() for s in seeds}
    if exclude_path:
        for line in open(exclude_path, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                blocked.add(domain(line.strip()) if "." in line else line.strip().lower())
    seen, rows, dropped = set(), [], Counter()
    for lead in leads:
        company = lead.get("Company Name") or ""
        dom = domain(lead.get("Company Domain") or lead.get("Company Website URL"))
        key = lead.get("Linkedin URL Unique ID") or lead.get("Sales Navigator URL")
        if key in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(key)
        if dom in blocked or company.lower() in blocked:
            dropped["customer or excluded company"] += 1
            continue
        if lead.get("Matches Filters") == "NO":
            dropped["outside the search filters (Evaboot check)"] += 1
            continue
        if (lead.get("Email Status") or "").lower() != "safe":
            dropped["email not safe"] += 1
            continue
        twin = max(seeds, key=lambda s: (s["industry"] == lead.get("Company Industry"))
                   + (s["employees"] == lead.get("Company Employee Range"))
                   + (region(s["location"]) == region(lead.get("Company Location", ""))))
        same = [label for label, ok in (
            ("industry", twin["industry"] == lead.get("Company Industry")),
            ("size", twin["employees"] == lead.get("Company Employee Range")),
            ("region", region(twin["location"]) == region(lead.get("Company Location", ""))),
        ) if ok]
        rows.append({
            "First name": lead.get("First Name", ""), "Last name": lead.get("Last Name", ""),
            "Job title": lead.get("Current Job", ""), "Company": company, "Domain": dom,
            "Industry": lead.get("Company Industry", ""), "Employees": lead.get("Company Employee Range", ""),
            "Company location": lead.get("Company Location", ""), "Email": lead.get("Email", ""),
            "Email status": lead.get("Email Status", ""), "LinkedIn": lead.get("Linkedin URL Public", ""),
            "Looks like": twin["name"], "Same as that customer": ", ".join(same) or "none",
        })
    w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]) if rows else ["First name"])
    w.writeheader()
    w.writerows(rows)
    print(f"{len(leads)} leads in the export, {len(rows)} kept with a safe email.", file=sys.stderr)
    for reason, n in dropped.most_common():
        print(f"- dropped {n}: {reason}", file=sys.stderr)


def main(argv):
    if len(argv) >= 3 and argv[1] == "profile":
        return cmd_profile(argv[2])
    if len(argv) >= 4 and argv[1] == "url":
        return cmd_url(argv[2], argv[3])
    if len(argv) >= 4 and argv[1] == "clean":
        exclude = argv[argv.index("--exclude") + 1] if "--exclude" in argv else None
        return cmd_clean(argv[2], argv[3], exclude)
    sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
