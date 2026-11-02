# Run it in n8n

[`n8n/lookalike-prospect-list.json`](../n8n/lookalike-prospect-list.json) builds the same list from an n8n form, when you prefer a form to a chat. `n8n/build_workflow.py` regenerates it.

## What runs

1. **Your best customers** (form): paste the `SEEDS.md` table, who you sell to (roles and region) and how many leads.
2. **Profile** (Code): finds the industries and sizes your customers share. It stops if an industry has no LinkedIn id yet: add it to `INDUSTRY` in that node.
3. **Build the people search** and **Check the build** (Evaboot MCP): the Sales Navigator search for the roles and region.
4. **Add lookalike filters** (Code): adds industry, company size and company headquarters, and excludes your customers.
5. **Review the search** (form): the link to the search and the cost. Nothing is spent until you choose *Export the leads*.
6. **Export with Evaboot** and **Check the export** (Evaboot MCP): the leads with verified emails.
7. **Clean rows** (Code): drops your customers, duplicates, leads outside the filters and emails that are not safe, and adds the customer each lead looks like.
8. **Add to your sheet** (Google Sheets): one row per lead.

## Set it up

1. **Import** the JSON: *Workflows > Import from file*.
2. **Add two credentials:**
   - **Bearer Auth** named `Evaboot MCP (Bearer)`: your key from [dash.evaboot.com/dash/api/](https://dash.evaboot.com/dash/api/). Select it on the four Evaboot MCP nodes.
   - **Google Sheets** on **Add to your sheet**.
3. **Create a sheet** and paste its URL, with the `gid` of the tab, into **Your settings**.
4. **Test:** open the form URL, paste your customers, and ask for 10 leads.

Back to the [README](../README.md).
