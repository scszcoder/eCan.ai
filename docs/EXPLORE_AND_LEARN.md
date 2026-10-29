# Explore and learn for browser skills

`agent/ec_skills/experience/` lets a browser skill get better by itself: a check
scores every run, methods that work are kept as **recipes**, and a part that keeps
failing is **explored** by a stronger model that finds a reliable method and saves it.
Nothing in it is specific to a platform, product or skill.

## Why it exists

On 2026-10-30 the 抖店 listing agent filled SKU codes wrong run after run. The SKU
table is a virtual list (about 8 of 18 rows drawn) whose 机型 cell is merged, so a
row scrolled away from its group's first row shows no 机型 and the agent guessed.
The learn step saw the symptom and wrote "never use a script for SKU codes" and
marked it verified, because it ran before the check and took "published" for
"right". The working method (write each row's values into the page's own form
store, matched by the row's spec values) was found by hand: read the page's data,
test write / read back / revert, then use it. That sequence is what this module
makes a step the skill takes itself.

## The loop

1. **Prompt** -- `ExperienceStore(folder).render(data)` lists the recipes (verified
   first, then candidates) with `__DATA__` in each script replaced by the run's
   input. Put it in the browser node's prompt next to the experience notes, and tell
   the agent recipes win over notes.
2. **Check** -- after the run, a code node compares the result with the source of
   truth (a read-only API is best) and decides, per *part* the skill cares about,
   whether it came out right: `{"标题": True, "规格编码": False, ...}`. Only parts the
   check actually saw go in.
3. **Grade** -- `store.grade(results)`: a candidate recipe whose part passed becomes
   `verified`; a candidate that failed is retired (`failed`); a verified one is
   retired after two failures. Consecutive failures are counted per part.
4. **Trigger** -- `store.explore_target(results, weights)` returns a part that failed
   `FAILS_TO_EXPLORE` (2) checks in a row, at most once per part per 12 h and twice
   per folder per day; among several, the one with most failures, then most
   mismatches (*weights*). Set it and `explore_prompt(...)` into attributes.
5. **Explore** -- a condition node (`attributes.get("explore_task")`) routes to an
   explore browser node: stronger model (default `qwen3.8-max`), capped steps
   (default 60), prompt = the explore task. It works on a **fresh create/new page**,
   finds where the page keeps that data, tests write -> read back -> revert, never
   saves or submits, and returns `{part, when, script, test, why}`.
6. **Keep** -- a code node runs `parse_recipe(final, part)` (needs `__DATA__`, max
   6000 chars, `{{`/`}}` split so the prompt renderer leaves it alone) and
   `store.add_recipe(...)`. The next run uses it; step 3 decides its fate.

## Wiring a skill (four nodes)

```
prepare  ->  browser (task)  ->  ... check (code) ->  condition ─if─> browser_explore -> code_recipe -> end
   render recipes                 grade + explore_target      └else─> end
```

- **prepare**: `attrs["recipes"] = ExperienceStore(folder).render(input_data)`; wrap the
  import in `try` so the skill still runs on an app without the module.
- **check**: build `results` from the check, then `grade`, then `explore_target`; on a
  hit set `attributes.explore_part` and `attributes.explore_task`.
- **condition** (custom expr): `attributes.get("explore_task")`; `if` -> explore,
  `else` -> end.
- **browser_explore**: copy of the task's browser node; system prompt forbids saving,
  submitting and sign-up buttons; model / max steps from the skill's config.
- **code_recipe**: `parse_recipe(final, attributes.explore_part)` -> `add_recipe`.

One folder per platform (or per platform and store) is the usual scope; the listing
skill uses `knowledge_service/listing_experience/<platform>/` next to its notes.

## Rules

- The check is the only judge. Notes and recipes are promoted only by a passing
  check, never by the agent's own report.
- Explore on a page you own and never save: a fresh create page, or the edit page of
  a test object. Never on a real product, order or customer record -- in real use the
  product just published is the merchant's live product.
- Recipes match items by their own identifiers (spec values, ids), never by position.
- Exploration costs real money on the customer's account: keep the caps.
