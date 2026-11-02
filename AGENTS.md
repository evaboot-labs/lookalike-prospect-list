# Agent instructions

This repo builds a B2B prospect list in one session from the user's best customers. Your AI Agent reads what 3 to 5 customers share (industry, company size, region), turns it into a LinkedIn Sales Navigator search for the people the user sells to at lookalike companies, exports them with verified emails through Evaboot, removes the customers and excluded companies, and writes a clean CSV or Google Sheet that says which customer each lead looks like.

1. Follow the skill in `skills/lookalike-prospect-list/SKILL.md` step by step.
2. The customers go in `SEEDS.md`. If it says `Status: EXAMPLE`, ask the user for their own customers and rewrite the table.
3. `lookalike.py` finds what the customers share, adds the filters to the search URL and cleans the export. Python 3, no packages.
4. If the Evaboot MCP tools are missing, follow `docs/connect-your-agent.md`.
5. If the user wants the list built in n8n instead, follow `docs/n8n.md` with them one step at a time.

Confirm with the user before every export (1 Evaboot credit per lead, email included) and before any push to a sheet or CRM. Never guess a customer's industry, size or location: read them from a real source. Never ask for or handle an API key: the user writes it into `.env`. Never commit `.env` or `data/`: they hold real people's data and secrets.
