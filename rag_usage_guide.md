# RAG Usage Guide (AppSync)

This guide explains how to use the AppSync APIs:

- `reqRAGStore(input: [RAGIN]!): AWSJSON!`
- `queryRAGs(qs: AWSJSON!): AWSJSON!`

to (1) ingest documents with metadata, and (2) query results intelligently using the **global universe + per-product filtering** approach.

## Mental model

- **Documents live in S3** under a per-user directory.
- **Indexing happens in a Fargate worker** which produces `chunks.json` in S3.
- `reqRAGStore` writes a per-user **doc registry** (`doc_registry.json`) that maps each document S3 key to metadata (pid/categories/version/etc).
- `queryRAGs` reads `chunks.json`, merges doc-registry metadata into each chunk, then filters by `pid` / `categories` before scoring and (optionally) synthesizing an answer.

### Important paths in S3

Per-user directory:
- `userDir = <cognito-sub OR sanitized-email>`

Per-product docs:
- `s3://$RAG_BUCKET/<userDir>/<pid>/docs/<filename>`

Per-product index:
- `s3://$RAG_BUCKET/<userDir>/<pid>/index/chunks.json`

Global index (all products under a user):
- `s3://$RAG_BUCKET/<userDir>/global/index/chunks.json`

Doc registry (metadata sidecar):
- `s3://$RAG_BUCKET/<userDir>/doc_registry.json`

## API reference

## 1) `reqRAGStore` — register doc metadata

**What it does**
- Upserts records in `doc_registry.json` keyed by `docKey`.
- The `docKey` is derived from: `<userDir>/<pid>/docs/<file>`.

**Input**

Your current schema includes:

```graphql
input RAGIN {
  categories: String!
  fid: ID!
  file: String!
  format: String!
  options: AWSJSON!
  pid: ID!
  version: String!
}

type Mutation {
  reqRAGStore(input: [RAGIN]!): AWSJSON!
}
```

**Notes**
- `categories` can be a single string or a delimiter-separated string (commas/`|`/`;`).
- `options` is stored as parsed JSON when possible.
- `fid` can be any stable ID you use for the file.

**Example mutation**

```graphql
mutation RegisterDocs($input: [RAGIN]!) {
  reqRAGStore(input: $input)
}
```

Variables example:

```json
{
  "input": [
    {
      "pid": "IC_007",
      "fid": "ds-001",
      "file": "IC_007_datasheet.pdf",
      "format": "pdf",
      "version": "revC-2026-01",
      "categories": "datasheet",
      "options": {"source": "vendor", "lang": "en"}
    },
    {
      "pid": "IC_007",
      "fid": "an-003",
      "file": "IC_007_appnote_motorcontrol.pdf",
      "format": "pdf",
      "version": "1.0",
      "categories": "app_note|motor_control",
      "options": {"app_domain": "motor_control"}
    }
  ]
}
```

Return payload is an `AWSJSON` string (JSON-encoded), for example:

```json
{"success": true, "count": 2, "docKeys": ["<userDir>/IC_007/docs/IC_007_datasheet.pdf", "<userDir>/IC_007/docs/IC_007_appnote_motorcontrol.pdf"]}
```

## 2) `queryRAGs` — query chunks with filters

**What it does**
- Loads `chunks.json` (prefers per-`pid` index, falls back to `global` index).
- Merges doc-registry metadata into `chunk.metadata`.
- Applies filters (`pid`, `categories`) and scores chunks.
- Returns `AWSJSON` (JSON-encoded) with `{ answer, chunks, query, mode }`.

**Schema**

```graphql
type Query {
  queryRAGs(qs: AWSJSON!): AWSJSON!
}
```

**Recommended `qs` structure**

```json
{
  "query": "How do I configure SPI mode 3?",
  "pid": "IC_007",
  "categories": "prog_guide|datasheet|errata",
  "topK": 8,
  "mode": "hybrid"
}
```

- `pid` is optional.
  - If omitted, you get “product selection mode” (global universe).
- `categories` is optional.
  - Use it to restrict the universe to doc types like `errata`, `prog_guide`, etc.

## End-to-end flows

## Flow A — per-product ingestion + query

1) Upload your files to S3 under `<userDir>/<pid>/docs/…`

In the web app, the typical flow is:
- `ragRequestUploadURLs` → PUT to presigned URLs → `ragConfirmUploads`

2) Register metadata with `reqRAGStore` for each file.

3) Trigger indexing for that product `pid` (so the worker builds `<pid>/index/chunks.json`).

4) Query with `queryRAGs({ pid: "IC_007", ... })`.

## Flow B — global universe (product selection mode)

1) Upload docs to multiple product pids.

2) Call `reqRAGStore` for each doc so categories/pid/version are recorded.

3) Trigger global indexing by running the worker with `pid=global`.
- This produces: `<userDir>/global/index/chunks.json`
- Each chunk is tagged with `metadata.pid` so you can filter later.

4) Query without `pid` to shortlist candidates, or query with `pid` to focus.

Example global query:

```json
{
  "query": "Which IC supports motor control at 24V and has SPI config registers?",
  "topK": 12,
  "categories": "datasheet|app_note"
}
```

Then follow up with a focused query:

```json
{
  "query": "Show the SPI init sequence and errata caveats",
  "pid": "IC_007",
  "categories": "prog_guide|errata",
  "topK": 10
}
```

## JavaScript examples (web)

Below are plain examples (no framework assumptions). If you already use Amplify or an existing API client, adapt the `graphqlRequest()` function.

### Example: call `reqRAGStore`

```js
async function graphqlRequest({ url, apiKey, query, variables }) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': apiKey,
    },
    body: JSON.stringify({ query, variables }),
  });
  const json = await res.json();
  if (json.errors?.length) throw new Error(json.errors[0].message);
  return json.data;
}

const MUTATION = `mutation RegisterDocs($input: [RAGIN]!) { reqRAGStore(input: $input) }`;

// NOTE: reqRAGStore returns AWSJSON string, so you usually JSON.parse() it.
const data = await graphqlRequest({
  url: process.env.APPSYNC_URL,
  apiKey: process.env.APPSYNC_API_KEY,
  query: MUTATION,
  variables: {
    input: [
      {
        pid: 'IC_007',
        fid: 'ds-001',
        file: 'IC_007_datasheet.pdf',
        format: 'pdf',
        version: 'revC-2026-01',
        categories: 'datasheet',
        options: { source: 'vendor' },
      },
    ],
  },
});

const result = JSON.parse(data.reqRAGStore);
console.log(result);
```

### Example: call `queryRAGs`

```js
const QUERY = `query QueryRAGs($qs: AWSJSON!) { queryRAGs(qs: $qs) }`;

const qs = {
  query: 'What is the max SPI clock?',
  pid: 'IC_007',
  categories: 'datasheet|prog_guide|errata',
  topK: 8,
};

const data = await graphqlRequest({
  url: process.env.APPSYNC_URL,
  apiKey: process.env.APPSYNC_API_KEY,
  query: QUERY,
  variables: { qs: JSON.stringify(qs) },
});

const out = JSON.parse(data.queryRAGs);
console.log(out.answer);
console.table(out.chunks.map(c => ({ score: c.score, source: c.source })));
```

## Python examples

These examples use an API key header for simplicity.

```python
import json
import requests

APPSYNC_URL = "https://<your-appsync-id>.appsync-api.<region>.amazonaws.com/graphql"
API_KEY = "<api-key>"


def gql(query: str, variables: dict):
    r = requests.post(
        APPSYNC_URL,
        headers={"content-type": "application/json", "x-api-key": API_KEY},
        data=json.dumps({"query": query, "variables": variables}),
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"][0]["message"])
    return payload["data"]


# --- reqRAGStore ---
REGISTER = """
mutation RegisterDocs($input: [RAGIN]!) {
  reqRAGStore(input: $input)
}
"""

data = gql(REGISTER, {
    "input": [
        {
            "pid": "IC_007",
            "fid": "ds-001",
            "file": "IC_007_datasheet.pdf",
            "format": "pdf",
            "version": "revC-2026-01",
            "categories": "datasheet",
            "options": {"source": "vendor"},
        }
    ]
})
print(json.loads(data["reqRAGStore"]))


# --- queryRAGs ---
QUERY_RAGS = """
query QueryRAGs($qs: AWSJSON!) {
  queryRAGs(qs: $qs)
}
"""

qs = {
    "query": "Does IC_007 have errata about ADC saturation?",
    "pid": "IC_007",
    "categories": "errata|datasheet",
    "topK": 10,
}

data = gql(QUERY_RAGS, {"qs": json.dumps(qs)})
out = json.loads(data["queryRAGs"])
print(out.get("answer"))
print("chunks:", len(out.get("chunks", [])))
```

## Troubleshooting

- **`queryRAGs` returns no chunks**
  - Ensure indexing has been run and `chunks.json` exists in S3.
  - For global mode, ensure `pid=global` indexing was triggered and completed.

- **Filtering by `pid` doesn’t work**
  - Ensure `chunks.json` contains `metadata.pid`. (Global indexing attaches this automatically; per-pid indexing will set pid too.)

- **Filtering by `categories` doesn’t work**
  - Ensure you called `reqRAGStore` for the docs and categories are present.
  - Categories are stored in the doc registry and merged into chunk metadata.

- **Doc revisions**
  - Call `reqRAGStore` again with a newer `version`, then re-index.

