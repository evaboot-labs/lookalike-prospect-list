---
name: lookalike-prospect-list
description: Build a B2B prospect list in one session from your best customers - read what 3 to 5 customers share (industry, company size, region), turn it into a LinkedIn Sales Navigator search for the people you sell to at lookalike companies, export them with verified emails through Evaboot, drop your customers and excluded companies, and write a clean CSV or Google Sheet with the customer each lead looks like. Use when the user asks to build a prospect list in Claude, find companies like their best customers, build a lookalike list, or turn their customer base into an ICP and a lead list.
---

# Lookalike prospect list

This skill runs inside a clone of https://github.com/evaboot-labs/lookalike-prospect-list: it uses the repo's `lookalike.py`, `SEEDS.md` and `docs/`. If `lookalike.py` is not in the working directory, clone the repo and work from there.

You do the Sales Navigator and Evaboot work through the Evaboot MCP server (`https://mcp.evaboot.com/mcp`). `lookalike.py` finds what the customers share, adds the filters to the search URL and cleans the export. It needs Python 3 and nothing else.

## Rules

- Confirm with the user before `export_sn_search_or_list` and before any push to a sheet or CRM. Show the number of leads and the cost (1 Evaboot credit per exported lead, email included), then wait for a yes.
- Take the customers' industry, size and location from a real source: the user's CRM, the company's LinkedIn page, or an Evaboot export. Never guess them.
- Never ask for or paste an API key. The user writes `EVABOOT_API_KEY` into `.env` (`docs/connect-your-agent.md`).
- Print every Sales Navigator URL as a Markdown link with the URL in angle brackets: `[Open in Sales Navigator](<url>)`.

## Step 0: check the setup

1. If the Evaboot MCP tools are missing, walk the user through `docs/connect-your-agent.md`, then ask them to restart the agent from this folder.
2. Call `get_daily_export_quota`. If `has_valid_salesnav` is false, ask the user to sign in to Evaboot in Chrome, open any Sales Navigator search with the Evaboot extension, and click **Export with Evaboot**, then call it again.
3. Run `mkdir -p data`.

## Step 1: the seeds

1. Ask for 3 to 5 of their best customers: the ones who bought fast, stayed and pay well. Ask who they sell to at those companies (roles) and how many leads they want (10 to 50 for a first list).
2. For each customer, fill one row of the `SEEDS.md` table: the LinkedIn company id (the number in `linkedin.com/company/<id>` or in the Sales Navigator company URL), the domain, the LinkedIn industry, the employee range (`51 to 200`, `201 to 500`...) and the location. Read them from the user's CRM connector if there is one, else ask the user to paste the LinkedIn company URLs and read the pages. Set `Status: yours`.
3. Run:

```bash
python3 lookalike.py profile SEEDS.md
```

4. Show the user what their customers share. Every value goes into the search, so ask about each value that only one customer has (`1/5`): it widens the list. To drop it, remove that customer from the table.
5. If it prints an unknown industry, ask the user to pick that industry in a Sales Navigator search, then read its id from the URL (`type:INDUSTRY ... id:<n>`) and add it to `INDUSTRY` in `lookalike.py`.

## Step 2: the search

1. Call `build_sn_search_from_prompt` with **the people part only**: the roles and the region from step 1, for example "Heads of Sales, VPs of Sales and Sales Directors based in Île-de-France, France". Leave the industry and the size out: in the request they start a slow company-first crawl. Pass `max_results`. Poll `get_search_build` until `complete`.
2. Add the customers' industry and size, and exclude the customers themselves:

```bash
python3 lookalike.py url "<the url>" SEEDS.md > data/search-url.txt
```

3. Show the user the search as a link and the roles it matches. Ask before you export.

## Step 3: export and clean

1. On a yes, call `export_sn_search_or_list` with the URL from `data/search-url.txt`, `name` "Lookalike list <date>" and `max_results`. Poll `get_export` with `limit: 0` until `EXECUTED`.
2. Save the leads: `set -a; . ./.env; set +a; curl -s -H "Authorization: Bearer $EVABOOT_API_KEY" https://api.evaboot.com/v1/extractions/<extraction_id>/ > data/export.json`. Without the API key, call `get_export` and write its JSON to `data/export.json`.
3. Clean it. `data/exclude.txt` is optional: one domain or company name per line (current customers, open deals, competitors).

```bash
python3 lookalike.py clean data/export.json SEEDS.md --exclude data/exclude.txt > data/list-$(date +%F).csv
```

4. Report what it printed: leads exported, leads kept, and why the others were dropped. Only leads with a `safe` email are kept.

## Step 4: where the list goes

Ask where they want it:

- **CSV:** the file in `data/`. Done.
- **Google Sheets:** import the CSV into a new tab (*File > Import*), or write the rows with a Google Sheets connector if the user has one.
- **A CRM or an outreach tool:** `list_integrations`. If the destination is connected, `push_export` with the `extraction_id` and poll `get_push`. This sends the whole export, before the clean-up, so tell the user. Otherwise import the CSV.

To repeat the list every week, see the AI lead finder: https://github.com/evaboot-labs/ai-lead-finder. To run it from n8n instead, follow `docs/n8n.md`.
