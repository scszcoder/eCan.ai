# lightrag_custom

eCan-specific patches on top of upstream LightRAG. **Not a fork of source code** —
only behavioral overrides that upstream does not (and intentionally does not) ship.

Last verified against upstream: **LightRAG v1.5.6**.

## Why this directory still exists after the 1.5 upgrade

A common audit question: *"the upstream code we used to patch is gone — do we still need this?"*

**Yes.** Two product behaviors are not provided by upstream and are not derivable
from the upstream API surface:

### 1. Filename deduplication

`utils_custom._deduplicate_filename` repairs parser artifacts that surface in
real document ingestion, e.g.

| Before | After |
|---|---|
| `产品产品说明书说明书.docx.docx` | `产品说明书.docx` |
| `file.tar.gz.tar.gz` | `file.tar.gz` |

The cleaned name is written back onto each chunk (`chunk["file_path"] = ...`,
line 90 of `utils_custom.py`) **before** the reference-list logic touches it.

**Why upstream cannot absorb this**: upstream `lightrag.utils.generate_reference_list_from_chunks`
(v1.5.6, `lightrag/utils.py:6079`) treats `file_path` as opaque and only filters
the empty/`"unknown_source"` cases. The deduplication is eCan's parser-side
contract; upstream has no opinion on it.

**Downstream impact if removed**:
`ConfidenceScorer._filter_references` keys its `seen_paths` set on the file_path
string (`knowledge/lightrag_confidence_scorer.py:651-654`). Without dedup,
`产品说明书.docx` and `产品产品说明书说明书.docx.docx` collapse to one entry visually
but remain two distinct file paths upstream — `ref_count` is inflated and the
*coverage* dimension of the confidence score drifts.

### 2. Per-reference score aggregation

`utils_custom.generate_reference_list_from_chunks_with_scores` collects
`rerank_score` / `score` / `similarity` / `(1 - distance)` from every chunk,
averages them by `file_path`, and attaches `ref_item["score"]`.

**Why upstream cannot absorb this**: upstream 1.5.6 still emits the bare
two-field reference item at `lightrag/utils.py:6140`:

```python
reference_list.append({"reference_id": str(i + 1), "file_path": file_path})
```

There is no score field. This was true in 1.4.9, was not changed in 1.5, and is
not on the upstream roadmap (LightRAG deliberately treats retrieval scores as a
query-time concern, not a reference-list concern).

**Downstream impact if removed**: `ConfidenceScorer._get_retrieval_signal`
falls through Priority 1 (chunk-level rerank) to Priority 2 (reference-level).
In deployments **without** a rerank model (the common production case),
Priority 1 yields nothing and Priority 2 needs `ref_item["score"]` to
populate the `retrieval_score` that feeds `_make_decision`'s
`low_retrieval` gate (`retrieval_score < 0.18 → reject`). Without this patch,
the gate is always tripped and every query is rejected as low-confidence.

## Why a full re-implementation, not a decorator on the upstream function

The patch duplicates roughly 50 lines of upstream logic (frequency counting,
reference_id assignment). The tempting simplification is to call the upstream
function and post-process its output. We deliberately don't.

Reasons:
- Upstream 1.4 → 1.5 already changed its internal ordering rules
  (frequency-first → frequency-then-appearance). If we'd been a wrapper in 1.4,
  the 1.5 upgrade would have silently altered our reference_id semantics.
- A re-implementation defines eCan's contract independently of upstream's
  internal representation. The contract surface is the
  `(reference_list, updated_chunks)` tuple plus the chunk fields we read.
- Cost is bounded: ~50 lines duplicated, no growth pressure across LightRAG
  versions.

## Why we patch both `lightrag.utils` and `lightrag.operate`

`lightrag/operate.py:18` is a `from lightrag.utils import (
    ...,
    generate_reference_list_from_chunks,
    ...
)` statement.

`from X import Y` creates a **value binding** in the importing module's
namespace at import time. After:

```python
lightrag.utils.generate_reference_list_from_chunks = patched
```

…`lightrag.operate.generate_reference_list_from_chunks` still points to the
original function, because `operate.py`'s namespace holds its own reference
captured at import. Calls from `operate.py:5315` and `operate.py:6215` therefore
would still hit the un-patched version unless we also write:

```python
lightrag.operate.generate_reference_list_from_chunks = patched
```

This is not optional, not redundant, and is not a sign of upstream refactoring
we should chase.

## When to revisit this directory

| Trigger | Action |
|---|---|
| Upstream emits a `score` field on reference items by default | Remove `generate_reference_list_from_chunks_with_scores`, keep only `_deduplicate_filename` as a separate concern |
| Upstream exposes a `filename_cleaner` hook in the document parser pipeline | Move `_deduplicate_filename` into the pipeline and drop it from here |
| Upstream stops using `from lightrag.utils import generate_reference_list_from_chunks` in `operate.py` (e.g. switches to lazy/qualified access) | Drop the second line in `patch_generate_reference_list_from_chunks` |
| Confidence gate is replaced by a different scoring strategy | Re-evaluate whether `reference_id` and `score` injection still feed anything |

Until two of the above happen, **this directory is load-bearing**. Do not delete
or skip `patch_generate_reference_list_from_chunks()` in the launcher.

## Contents

| File | Purpose |
|---|---|
| `utils_custom.py` | Filename dedup + score-injected reference list + double-module patch (utils + operate) |
| `__pycache__/` | Python bytecode cache (regenerated on next import) |

There is intentionally **no `__init__.py`** — the module is loaded via
`from utils_custom import ...` (sys.path-top-level) from
`knowledge/lightrag_launcher.py`, not as a package.