# Building a Flowgram Skill That Actually Runs

Written 2026-09-17, after taking one `browser_automation` skill from "dies 30
seconds in, before any model call" to "drives eBay, reports by email". Read
this BEFORE designing a new skill — most of what follows is not discoverable
from the node editor.

Companion: `BROWSER_AUTOMATION_ADSPOWER_POSTMORTEM.md` (the infrastructure
chain), `EBAY_AFTER_SALES_PROMPT_CONTRACT.md` (a worked prompt).

---

## 1. The shape to build

**One loop, one browser node, one MCP node. Put the work in the prompt.**

```
start → loop { browser_automation } → mcp (auto-select) → end
```

That is the whole diagram for a real after-sales agent handling four queues,
label downloads, printing and email. Everything that looks like it wants to be
a node — "check orders", "process returns", "decide what to do next" — belongs
in the prompt instead. The model is better at branching than the graph is, and
every node you add is another place for state to not arrive.

Why this shape and not more:

- **Nodes are expensive to debug.** Each one has its own config, its own
  normalizer, its own way of not receiving what you think it receives. The
  chain in the postmortem broke in seven places, all of them BETWEEN nodes.
- **The prompt is the cheap, fast part to change.** A prompt edit is seconds
  and needs no restart of your thinking. A graph edit changes state plumbing.
- **The loop already gives you iteration.** You do not need a node per queue;
  you need one turn per item and a prompt that says which queue to work next.

### The loop

Set `loopMode: loopWhile` and keep the condition trivial:

```python
not (((state.get("result") or {}).get("llm_result") or {}).get("all_done") or False)
```

Non-obvious and expensive to learn:

- **The loop is a WHILE, not a do-while.** `update → check → body`. The
  condition is evaluated BEFORE the first iteration.
- **On entry `llm_result` is pre-seeded** `{'all_done': False, 'work_done': False}`
  — byte-identical to what a "nothing to do" turn produces. You therefore
  CANNOT distinguish first-entry from finished-with-nothing using those fields.
  A condition requiring `work_done` true never runs the body at all.
- Use `.get()` chains, not `state["result"]["llm_result"]["all_done"]`. A
  missing key should exit, not raise mid-run.
- The exit decision belongs to the AGENT, in the prompt. Only it knows the
  board is empty.

### The trailing MCP node

Leave `tool_name` empty — that turns on LLM auto-select. The browser node hands
it work by emitting a tool-call block; see §3.

---

## 2. Put the workload in the prompt

The prompt is where the branching, the priorities, the stop conditions and the
output contract live. A good one for this kind of skill has:

1. **Scope per turn** — "one item per turn", "no more than 15 steps on an item",
   "an item you skip is cheap; a turn that dies costs the whole cycle".
2. **A priority queue** — which queue to work first, what to do when each is
   empty.
3. **Stop conditions, stated as facts not hopes** — signed out, captcha,
   page will not load, proxy down. Say what to do: do NOT sign in, do NOT
   retry forever, report and end the turn.
4. **An output contract** — one bare JSON object, `json.loads`-parseable, no
   markdown fences.
5. **A handoff block** — the tool call the MCP node will run (§3).
6. **Where things go** — download directories, file naming, printer, report
   recipients, all via `{{vars}}`.

### The output contract

```json
{"task_completed": "process_orders",
 "system_errors": "",
 "work_summery": "markdown, what you did and what you left",
 "work_done": true,
 "all_done": false}
```

Rules worth copying verbatim:

- `all_done: true` when there is nothing left — **including when every queue was
  empty**. "Nothing to do" is a finished turn, not an unfinished one. Getting
  this wrong is an infinite loop.
- `all_done: true` also on a blocking system fault. Nothing about a dead proxy
  or a logged-out session improves by repeating the same turn.
- `work_done` must be emitted explicitly. The runtime reports it in
  `llm_result`, but nothing puts it there unless the prompt asks.
- Keep the worked example in the prompt consistent with the rules. The model
  copies the example far more reliably than it follows the prose.

### Variables

Declare them in Skills > Metadata > Required Inputs; fill them per task in the
task's 任务变量. A `{{var}}` typed into a prompt is invisible until declared —
the skill editor now scans prompts on save and declares them for you.

A variable whose name contains `printer` renders a printer dropdown.

---

## 3. Handing work to tools

The browser node cannot print, cannot send mail, and cannot call MCP tools. It
hands work to the trailing MCP node by appending ONE json block after its
contract object:

```json
{
  "multi_tool_calls": "serial",
  "tool": [
    {"tool_name": "reformat_labels", "tool_input": {...}, "pipe_output_to": "file_names"},
    {"tool_name": "print_labels",    "tool_input": {"printer": "{{printer_name}}"}},
    {"tool_name": "send_email",      "tool_input": {"input": {"to": "...", "cc": ["..."]}}}
  ]
}
```

Hard-won details:

- **Use the MCP tool name, not the browser action name.** `send_email` is
  MCP-registered; `bu_send_email` is a browser-use action and is NOT in
  `tool_function_mapping` — in fact NO `bu_*` tool is. Calling one fails and
  (until 2026-09-17) reported success anyway.
- **Respect the tool's real schema.** `to` is a string, `cc`/`bcc` are ARRAYS.
  The MCP layer validates before the tool body runs, so a comma string is
  rejected even though the tool itself would have accepted it. Check
  `mcp_tools_schema.json`, not the pydantic action.
- **Most tools want the `{"input": {...}}` wrapper.** The compact prompt strips
  it when showing params, so the model does not see it — say it explicitly.
- **`pipe_output_to` beats `{{alias}}`** for passing a file list between tools:
  the alias substitutes the tool's TEXT result (prose), while `pipe_output_to`
  injects into a named field and is cleared if the source failed.
- **Do not expect the model to emit the block reliably.** Measured across two
  models: roughly half the time. Anything that MUST happen — a failure report,
  a notification — needs a code-side fallback, not better wording.

---

## 4. Node settings that matter more than they look

| setting | why |
|---|---|
| `allowedActions` | **Set this.** Every registered action is serialized into the request on EVERY step: 57 actions = 66KB, against a ~100KB body cap. An eBay node needs ~13. Also cuts input tokens on every step. |
| `excludedActions` | Applied after the allow-list. Put `screenshot` here when vision is off. |
| `useVision` | Off unless you need it — and note browser-use captures a screenshot anyway unless you suppress it (we do). |
| `maxSteps` | Per turn, not per run. 15 is sane for an item-at-a-time prompt. |
| `domLimit` | Usually leave unset. On a real page the DOM was 17.7KB of a 107KB body — capping it bought nothing. Measure before turning this knob. |
| `modelProvider` / `modelName` | eCanAI + a model the proxy serves. Fetch the list from the proxy rather than guessing names. |

---

## 5. Where the files actually are

This cost more time than any bug.

| thing | real location |
|---|---|
| skill graph | `my_skills/<skill>/diagram_dir/<skill>_skill_BUNDLE.json` — nodes at `sheets[0].document.nodes`. The non-bundle `<skill>_skill.json` (nodes at `workFlow.nodes`) is NOT what the loader reads. |
| prompt | `<user>_local/my_prompts/<name>_<id>.json` — the PER-USER dir, not the repo-root `my_prompts/`. Also exists in the cloud; **the desktop reads the file** and nothing reconciles the two. |
| settings | `browser_use_settings.json` at `getECBotDataHome()` |

**The running app rewrites the skill JSON from its own in-memory copy.** Editing
those files while it runs is unreliable — an edit was silently reverted that
way. Prefer the editor UI, or edit with the app closed, and always confirm the
setting appears in the next run's log.

---

## 6. How to tell whether your change took effect

Never assume. Each of these is one grep:

```
[BrowserAutomation] action filter: 57 -> 13 actions     # allowedActions
[BrowserAutomation] ✅ Resolved prompts - system: N chars # which prompt text
[BA._auto] preflight_done ... task_len=N                 # prompt + input
[condition-eval] expr='...' result=True|False            # loop condition
[BrowserAutomation][ResultWrite] propagated {...}         # agent flags -> loop
[MCP Auto-Select] lifted multi-tool wrapper: N call(s)    # handoff reached MCP
[MCP Multi-Tool] Completed N tool(s) (N succeeded)        # tools ran
```

If the prompt length does not match the file you edited, you edited the wrong
copy. That single line would have saved an hour.

---

## 7. Lessons that generalise

1. **An empty error message is the bug to fix first.** Six identical failures
   with nothing after the colon cost an afternoon. Three separate causes were
   hiding behind it. Do not theorise about a failure until it can describe
   itself.
2. **A silent no-op is indistinguishable from unreleased code.** Log the skip
   as well as the success. This cost a run three separate times in one day.
3. **A false success is worse than a failure.** Two tools reported success
   while doing nothing; the chain was twice declared complete while sending no
   mail. Check the tool's actual return, not the summary line.
4. **Measure before turning a knob.** "The page is too big" was a plausible
   premise, wrong by 62%, and one log line would have said so. The schema was
   the bulk, not the DOM.
5. **Read the library source instead of re-running.** The 30-second timeout was
   a constant in `browser_use/browser/events.py`.
6. **Ask the cloud what it stored.** One read-only `queryAgents` retired a
   nine-site "bug" that would have been nine pointless edits.
7. **Prompt compliance is ~50% for anything appended after the main answer.**
   If it must happen, put a fallback in code.
8. **Probe the API before believing a limitation.** "deepseek cannot do
   structured output" was wrong — it cannot do `json_schema`, but native tool
   calling works once thinking mode is disabled. That turned a workaround into
   the intended mechanism.
