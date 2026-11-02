"""Builds n8n/lookalike-prospect-list.json. Run: python3 n8n/build_workflow.py

A form takes your best customers (the SEEDS.md table), who you sell to and how many leads you want. A Code node
finds what the customers share, Evaboot builds the people search, a second Code node adds the customers'
industries, sizes and headquarters region and excludes the customers. A review page shows the search and the
cost; only on your yes does Evaboot export the leads, and the clean rows land in your Google Sheet.
"""
import json
import uuid
from pathlib import Path

MCP = "https://mcp.evaboot.com/mcp"
EVABOOT_CRED = {"httpBearerAuth": {"id": "", "name": "Evaboot MCP (Bearer)"}}
SHEETS_CRED = {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets account"}}
FORM = "Your best customers"
HEADCOUNT = {"1 to 10": "B", "11 to 50": "C", "51 to 200": "D", "201 to 500": "E", "501 to 1000": "F",
             "1001 to 5000": "G", "5001 to 10000": "H", "10001+": "I"}
INDUSTRY = {"Software Development": 4, "Technology, Information and Internet": 6, "Financial Services": 43,
            "IT Services and IT Consulting": 96, "Business Consulting and Services": 11, "Advertising Services": 80}

nodes, connections = [], {}


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos, **extra}
    if creds:
        n["credentials"] = creds
    nodes.append(n)


def link(a, b, out=0):
    connections.setdefault(a, {}).setdefault("main", [])
    while len(connections[a]["main"]) <= out:
        connections[a]["main"].append([])
    connections[a]["main"][out].append({"node": b, "type": "main", "index": 0})


def mcp_call(name, tool, json_expr, pos):
    node(name, "@n8n/n8n-nodes-langchain.mcpClient", 1.1, {
        "endpointUrl": MCP, "authentication": "bearerAuth",
        "tool": {"__rl": True, "mode": "list", "value": tool, "cachedResultName": tool},
        "inputMode": "json", "jsonInput": json_expr, "options": {"timeout": 120000},
    }, pos, EVABOOT_CRED)


def code(name, js, pos):
    node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos)


def is_equal(name, left, right, pos):
    node(name, "n8n-nodes-base.if", 2.2, {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
        "conditions": [{"id": str(uuid.uuid4()), "leftValue": left, "rightValue": right,
                        "operator": {"type": "string", "operation": "equals"}}],
        "combinator": "and"}, "options": {}}, pos)


PROFILE_JS = r"""
// Same as lookalike.py profile: read the seed table, count what the customers share.
const HEADCOUNT = __HEADCOUNT__, INDUSTRY = __INDUSTRY__;
const seeds = String($('__FORM__').first().json['Best customers (the SEEDS.md table)']).split('\n')
  .map(l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim()))
  .filter(c => c.length >= 6 && c[0] && c[0] !== 'Company' && !/^[-: ]+$/.test(c[0]))
  .map(c => ({ name: c[0], id: c[1].replace(/\D/g, ''), domain: c[2].toLowerCase(), industry: c[3], employees: c[4], location: c[5] }));
if (seeds.length < 2) throw new Error('Paste at least 2 customers as table rows: | Company | LinkedIn id | Domain | Industry | Employees | Location |');
const uniq = a => [...new Set(a)];
const industries = uniq(seeds.map(s => s.industry)), sizes = uniq(seeds.map(s => s.employees));
const unknown = industries.filter(i => !(i in INDUSTRY));
if (unknown.length) throw new Error('Add the LinkedIn id of these industries to INDUSTRY in this node: ' + unknown.join(', '));
return [{ json: { seeds, industry_ids: industries.map(i => INDUSTRY[i]), headcount_codes: sizes.map(s => HEADCOUNT[s]).filter(Boolean).sort(),
  exclude_company_ids: seeds.map(s => s.id).filter(Boolean),
  summary: `${seeds.length} customers: ${industries.join(', ')}; ${sizes.join(', ')}` } }];
""".replace("__HEADCOUNT__", json.dumps(HEADCOUNT)).replace("__INDUSTRY__", json.dumps(INDUSTRY)).replace("__FORM__", FORM)

FILTERS_JS = r"""
// Same as lookalike.py url: add the customers' industries, sizes and headquarters region, exclude the customers.
const p = $('Profile').first().json;
let url = $json.structuredContent?.result?.url;
if (!url || !url.includes('filters%3AList(')) throw new Error('Evaboot returned no people search URL: ' + JSON.stringify($json.structuredContent?.result).slice(0, 300));
const list = (type, vals, sel = 'INCLUDED') => `(type%3A${type}%2Cvalues%3AList(${vals.map(v => `(id%3A${v}%2CselectionType%3A${sel})`).join('%2C')}))`;
const parts = [];
if (p.industry_ids.length) parts.push(list('INDUSTRY', p.industry_ids));
if (p.headcount_codes.length) parts.push(list('COMPANY_HEADCOUNT', p.headcount_codes));
const regions = url.match(/type%3AREGION%2Cvalues%3AList\(((?:\(id%3A\d+%2CselectionType%3AINCLUDED\)(?:%2C)?)+)\)/);
if (regions && !url.includes('COMPANY_HEADQUARTERS')) parts.push(`(type%3ACOMPANY_HEADQUARTERS%2Cvalues%3AList(${regions[1]}))`);
if (p.exclude_company_ids.length) parts.push(list('CURRENT_COMPANY', p.exclude_company_ids.map(i => encodeURIComponent(encodeURIComponent('urn:li:organization:' + i))), 'EXCLUDED'));
if (!parts.length) throw new Error('No lookalike filter to add: the seeds have no known industry, size or LinkedIn id.');
url = url.replace('filters%3AList(', 'filters%3AList(' + parts.join('%2C') + '%2C');
return [{ json: { url, count: $json.structuredContent.result.result_count } }];
"""

ROWS_JS = r"""
// Same as lookalike.py clean: drop customers, duplicates, leads outside the filters and unsafe emails;
// say which customer each lead looks like.
const seeds = $('Profile').first().json.seeds;
const region = l => String(l || '').split(',').map(s => s.trim()).slice(-2).join(', ');
const blocked = new Set(seeds.flatMap(s => [s.domain, s.name.toLowerCase()]).filter(Boolean));
const seen = new Set(), rows = [];
for (const x of $json.structuredContent?.result?.prospects || []) {
  const key = x['Linkedin URL Unique ID'] || x['Sales Navigator URL'];
  if (seen.has(key)) continue; seen.add(key);
  if (blocked.has((x['Company Domain'] || '').toLowerCase()) || blocked.has((x['Company Name'] || '').toLowerCase())) continue;
  if (x['Matches Filters'] === 'NO' || String(x['Email Status']).toLowerCase() !== 'safe') continue;
  const same = s => [['industry', s.industry === x['Company Industry']], ['size', s.employees === x['Company Employee Range']],
    ['region', region(s.location) === region(x['Company Location'])]].filter(([, ok]) => ok).map(([k]) => k);
  const twin = seeds.reduce((a, b) => same(b).length > same(a).length ? b : a);
  rows.push({ json: { 'First name': x['First Name'], 'Last name': x['Last Name'], 'Job title': x['Current Job'],
    Company: x['Company Name'], Domain: x['Company Domain'], Industry: x['Company Industry'], Employees: x['Company Employee Range'],
    'Company location': x['Company Location'], Email: x['Email'], 'Email status': x['Email Status'],
    LinkedIn: x['Linkedin URL Public'], 'Looks like': twin.name, 'Same as that customer': same(twin).join(', ') || 'none' } });
}
if (!rows.length) throw new Error('No lead kept: none had a safe email inside the filters.');
return rows;
"""

node(FORM, "n8n-nodes-base.formTrigger", 2.2, {
    "formTitle": "Build a lookalike prospect list",
    "formDescription": "Paste 3 to 5 of your best customers. Evaboot builds the Sales Navigator search for the people you sell to at companies like them, and you decide before any credit is spent.",
    "formFields": {"values": [
        {"fieldLabel": "Best customers (the SEEDS.md table)", "fieldType": "textarea", "requiredField": True,
         "placeholder": "| MyTower | 11173669 | mytower.co | Software Development | 201 to 500 | Paris, Île-de-France, France |"},
        {"fieldLabel": "Who you sell to (roles and region)", "fieldType": "textarea", "requiredField": True,
         "placeholder": "Heads of Sales, VPs of Sales and Sales Directors based in Île-de-France, France"},
        {"fieldLabel": "Leads to export", "fieldType": "number", "requiredField": True, "placeholder": "10"},
    ]},
    "responseMode": "lastNode", "options": {},
}, [0, 0])
node("Your settings", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
    {"id": str(uuid.uuid4()), "name": "sheet_url", "type": "string", "value": "PASTE_YOUR_GOOGLE_SHEET_URL_WITH_GID"},
]}, "includeOtherFields": True, "options": {}}, [220, 0])
code("Profile", PROFILE_JS, [440, 0])
mcp_call("Build the people search", "build_sn_search_from_prompt",
         f"={{{{ JSON.stringify({{ prompt: $('{FORM}').first().json['Who you sell to (roles and region)'], "
         f"max_results: Number($('{FORM}').first().json['Leads to export']) || 10 }}) }}}}", [660, 0])
node("Wait 20 s", "n8n-nodes-base.wait", 1.1, {"amount": 20}, [880, 0])
mcp_call("Check the build", "get_search_build",
         "={{ JSON.stringify({ build_id: $('Build the people search').first().json.structuredContent.result.build_id }) }}",
         [1100, 0])
is_equal("Built?", "={{ $json.structuredContent.result.status }}", "complete", [1320, 0])
code("Add lookalike filters", FILTERS_JS, [1540, 0])
node("Review the search", "n8n-nodes-base.form", 2.3, {
    "formFields": {"values": [{"fieldLabel": "What next?", "fieldType": "dropdown", "requiredField": True,
                               "fieldOptions": {"values": [{"option": "Export the leads"}, {"option": "Stop here"}]}}]},
    "options": {"formTitle": "={{ $('Profile').first().json.summary }}",
                "formDescription": "=Exporting costs 1 Evaboot credit per lead, email included "
                                   "({{ $('" + FORM + "').first().json['Leads to export'] }} leads). "
                                   "<a href=\"{{ $json.url }}\" target=\"_blank\">Open the search in Sales Navigator</a>"},
}, [0, 400])
is_equal("Export?", "={{ $json['What next?'] }}", "Export the leads", [220, 400])
mcp_call("Export with Evaboot", "export_sn_search_or_list",
         "={{ JSON.stringify({ search_url: $('Add lookalike filters').first().json.url, "
         f"max_results: Number($('{FORM}').first().json['Leads to export']) || 10, "
         "name: 'Lookalike list ' + $now.toFormat('yyyy-MM-dd') }) }}", [440, 400])
node("Wait 30 s", "n8n-nodes-base.wait", 1.1, {"amount": 30}, [660, 400])
mcp_call("Check the export", "get_export",
         "={{ JSON.stringify({ extraction_id: $('Export with Evaboot').first().json.structuredContent.result.extraction_id }) }}",
         [880, 400])
is_equal("Done?", "={{ $json.structuredContent.result.status }}", "EXECUTED", [1100, 400])
code("Still running?", r"""
// Stop instead of waiting forever when the export failed.
const r = $json.structuredContent.result;
if (r.failure_reason || /FAIL|ERROR|CANCEL/i.test(r.status || '')) throw new Error(`The export stopped: ${r.status} ${r.failure_reason || ''}`);
return [$input.first()];
""", [1100, 560])
code("Still building?", r"""
// Stop instead of polling forever when the search build failed.
const r = $json.structuredContent.result;
if (r.failure_reason || /FAIL|ERROR|CANCEL/i.test(r.status || '')) throw new Error(`The search build stopped: ${r.status} ${r.failure_reason || ''}`);
return [$input.first()];
""", [1320, 160])
code("Clean rows", ROWS_JS, [1320, 400])
node("Add to your sheet", "n8n-nodes-base.googleSheets", 4.7, {
    "operation": "append",
    "documentId": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "sheetName": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
    "options": {},
}, [1540, 400], SHEETS_CRED)
node("Leads saved", "n8n-nodes-base.form", 2.3, {
    "operation": "completion", "completionTitle": "Your list is in your sheet",
    "completionMessage": "={{ $('Clean rows').all().length }} leads with a safe email, each with the customer it looks like.",
    "options": {}}, [1760, 400], executeOnce=True)
node("Stopped", "n8n-nodes-base.form", 2.3, {
    "operation": "completion", "completionTitle": "Nothing exported",
    "completionMessage": "No credit was spent. Change your customers or roles and submit the form again.", "options": {}},
    [440, 600])

for a, b in [(FORM, "Your settings"), ("Your settings", "Profile"), ("Profile", "Build the people search"),
             ("Build the people search", "Wait 20 s"), ("Wait 20 s", "Check the build"), ("Check the build", "Built?"),
             ("Add lookalike filters", "Review the search"), ("Review the search", "Export?"),
             ("Export with Evaboot", "Wait 30 s"), ("Wait 30 s", "Check the export"), ("Check the export", "Done?"),
             ("Still running?", "Wait 30 s"), ("Clean rows", "Add to your sheet"), ("Add to your sheet", "Leads saved")]:
    link(a, b)
link("Built?", "Add lookalike filters", out=0)
link("Built?", "Still building?", out=1)
link("Still building?", "Wait 20 s")
link("Export?", "Export with Evaboot", out=0)
link("Export?", "Stopped", out=1)
link("Done?", "Clean rows", out=0)
link("Done?", "Still running?", out=1)

workflow = {"name": "Lookalike prospect list (Evaboot MCP)", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {}}
out = Path(__file__).with_name("lookalike-prospect-list.json")
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
print(out, len(nodes), "nodes")
