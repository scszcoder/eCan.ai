# amazon_listing

Browser actions for listing on Amazon through Seller Central's
**Add Products via Upload** (category flat file, no SP-API):

| Action | Does | Returns |
|---|---|---|
| `amazon_download_template` | generate + download the category template, target store ticked and verified | `template`, `picked`, `stores` |
| `amazon_upload_flatfile` | stage the `.txt` through the real file input, submit | `batch_id`, `detected`, `region_error` |
| `amazon_fetch_report` | find the batch on Check Upload Status, download its Processing Summary | `row`, `report` |

The spreadsheet half runs as MCP tools (`agent/mcp/server/integrations/amazon_listing_tools.py`):
`amazon_template_inspect` -> `amazon_template_fill` -> upload -> fetch report ->
`amazon_parse_feedback`, looping on the named field errors until `done`.

The browser must already be signed in to Seller Central for the target marketplace.
Downloads land in the browser's downloads path (override with `downloads_dir`).

These actions are on the shared controller, so every browser node sees them;
a node that should not can list them in `excludedActions` (or scope itself with
`allowedActions`).

Ported from vibe-seller (Apache-2.0); see `agent/ec_skills/listing/amazon_flatfile/NOTICE`.
