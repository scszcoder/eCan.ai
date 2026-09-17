# eBay after-sales prompt — sections to add

**APPLIED to the live prompt `pr-665505` on 2026-09-17** (cloud, owner
`o3YBk2…`, mdContent 5173 -> 8682 chars). This file is the record of what was
changed and why, not a to-do.

The prompt is cloud-only — it is not in `my_prompts/` and not in any local
SQLite table, so the CLI cannot see it. It is reachable directly over GraphQL
(`queryPrompts` / `updatePrompts`) with no app running; see the note at the end
about the escaping bug that blocked the first attempt.

Three changes: label download + naming, the `all_done`/`work_done` contract that
lets the loop exit, and the end-of-turn tool call the MCP node auto-selects.

Uses the variables the prompt already declares: `{{docs_dir}}`,
`{{printer_name}}`, `{{summary_emails}}`.

---

## 1. Shipping labels — where they go and what they are called

```
## Downloading shipping labels

When you buy or retrieve a shipping label, download it yourself — do not leave it
in the browser's download folder.

Directory, exactly:

    {{docs_dir}}/labels/<RUNSTAMP>/

`<RUNSTAMP>` is the UTC time you started this turn, formatted `yyyymmddhhmmss`
(e.g. `20260917104233`). Use the SAME stamp for every label in this turn, so one
run's labels sit together in one folder. The directory is created for you — you
do not need a separate step to make it.

File name, exactly:

    <recipient>_<product>_<qty>.pdf

  - `<recipient>` — the buyer's name, lowercase, spaces and punctuation replaced
    by `-` (`John A. Smith` -> `john-a-smith`).
  - `<product>`  — a shorthand you invent, **at most 9 characters**, lowercase,
    no spaces. It must be instantly recognisable to a packer standing at a
    shelf: prefer the distinguishing word over the brand
    (`Blue Ceramic Mug 12oz` -> `mug12oz`, `USB-C Cable 2m` -> `usbc2m`).
  - `<qty>`      — the quantity as a plain integer (`1`, `3`).

Example: `john-a-smith_mug12oz_2.pdf`

Use `download_file` with the full absolute path. If eBay gives the file a random
name, download it and then use `rename_file` to put it right. Use `list_files`
on the directory afterwards to confirm what actually landed, and record every
final absolute path — you will need them in the tool call below.

Never invent a path you have not confirmed with `list_files`.
```

---

## 2. Finishing: what `all_done` means

```
## When the turn is finished

Return `all_done: true` when there is nothing left for anyone to do — INCLUDING
the case where every queue you checked was empty. "No work to do" is a finished
turn, not an unfinished one.

Return `all_done: false` ONLY when you did some work this turn and more work of
the same kind is still waiting.

Set `work_done: true` if you changed anything at all this turn (bought a label,
answered a case, accepted a return). Set `work_done: false` if you only looked.

The outer loop calls you again only while `all_done` is false AND `work_done` is
true. Reporting `all_done: false` with `work_done: false` ends the run — which
is correct when the queues are empty, and wrong if you simply gave up early.
```

---

## 3. The end-of-turn tool call (reformat → print → email)

```
## Handing off to the tools

When you have labels to hand over, end your final answer with ONE json block in
exactly this shape. A downstream node reads it and runs the three tools in
order. Emit it only when at least one label was downloaded; omit it entirely
otherwise.

{
  "multi_tool_calls": "serial",
  "tool": [
    {
      "tool_name": "reformat_labels",
      "tool_input": {
        "in_files": [
          {"file_name": "<absolute path of label 1>",
           "added_note_text": "<product shorthand> x<qty> - <recipient>"},
          {"file_name": "<absolute path of label 2>",
           "added_note_text": "<product shorthand> x<qty> - <recipient>"}
        ],
        "out_dir": "{{docs_dir}}/labels/<RUNSTAMP>/print",
        "sheet_width": 8.5,
        "sheet_height": 11.0,
        "label_width": 6.0,
        "label_height": 4.0,
        "label_orientation": "landscape",
        "label_rows_per_sheet": 2,
        "label_cols_per_sheet": 1,
        "label_rows_pitch": 0,
        "label_cols_pitch": 0,
        "top_side_margin": 0.25,
        "left_side_margin": 0.25,
        "add_backup": true
      },
      "pipe_output_to": "file_names"
    },
    {
      "tool_name": "print_labels",
      "tool_input": {
        "printer": "{{printer_name}}",
        "n_copies": 1
      }
    },
    {
      "tool_name": "bu_send_email",
      "tool_input": {
        "to": "<one address only>",
        "subject": "eBay after-sales - <RUNSTAMP> - <n> label(s)",
        "body_text": "<what you did this turn: orders shipped, labels printed, anything that needs a human>"
      }
    }
  ]
}

Rules for that block:

  - One entry in `in_files` per label. `added_note_text` is what gets printed on
    the backup copy, so it must be readable across a desk: product shorthand,
    quantity, recipient.
  - `add_backup: true` is required — it produces the second sheet the packer
    keeps as proof of shipment.
  - Do NOT fill `file_names` on `print_labels`. `pipe_output_to` injects the
    reformatted file paths from the previous tool automatically, and it is
    cleared if reformatting failed, so nothing bad gets printed.
  - `to` takes exactly ONE address. Additional recipients go in `cc` or `bcc`,
    which accept either a list or a comma-separated string.
  - Two labels are laid out per sheet in landscape. Do not change the sheet or
    label geometry.
```

---

## Notes

- **Why `pipe_output_to` rather than `{{reformat_labels}}`:** the `{{alias}}`
  placeholder substitutes the tool's *text* result, which for a reformat is
  prose, not a clean path list. `pipe_output_to` hands the result to the named
  field directly and is cleared when the source tool fails
  (`docs/MULTI_TOOL_CALLS.md`).
- **Why the browser node emits the JSON rather than the MCP node deciding:** the
  MCP node's auto-select LLM sees parameter *names only, no types*
  (`docs/MCP_TOOL_AUTO_SELECT.md`), so it cannot invent the label geometry or
  the file paths. The browser node is the only thing that knows which files it
  downloaded.
- The node's allowed actions are `navigate, click, input, extract, scroll, wait,
  go_back, find_text, switch, done, download_file, rename_file, list_files`, with
  `screenshot` excluded. Any tool named in the prompt but not on that list will
  silently not exist — update `allowedActions` on the node if this prompt grows.

---

## Why the loop never exited (the actual root cause)

The old contract said `all_done` is true *"only when every queue above is empty
**and the work report has been produced**"*, and "Where things go" told the agent
to print the labels and mail the report itself.

It has no tool for either — `print_labels` and `bu_send_email` are not on the
node's allowed-action list, and never were. So the agent could never finish the
report step, could never justify `all_done: true`, and the loop ran forever on
an empty board. `MCP_1` sits after the loop, so the email node was unreachable
too. That is why no mail ever arrived.

The fix splits the responsibility: the browser node downloads and names the
labels, and *emitting the handoff block* is what "producing the work report"
now means. Printing and mailing belong to the tools behind the MCP node.

`work_done` did not exist in the prompt at all, though the runtime reports it in
`llm_result`. The loop condition now requires it, so the prompt has to emit it —
that is why it is in the output contract above.

## Updating this prompt again

`gen_update_prompts_string` double-escaped its payload: `json.dumps` already
writes an inner quote as `\"`, and the old code then replaced `"` with `\"`
over that, producing `\\"` — GraphQL reads `\` as one literal backslash and
the `"` after it CLOSES the string. Any prompt containing a double quote failed
with `GRAPHQL_PARSE_FAILED`, which includes every prompt with a JSON example in
it. Fixed via `_gql_json_literal` (escape backslashes first, then quotes).

~59 other call sites in `cloud_api.py` still use the naive idiom. They are only
correct for payloads with no quotes and no backslashes.
