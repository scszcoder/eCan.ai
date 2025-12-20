# Mapping DSL for Node State and Resume Payload
 
> Note: This document has moved to the Skill Editor docs. Please see the canonical version here: [gui_v2/src/modules/skill-editor/doc/mapping-dsl.md](../gui_v2/src/modules/skill-editor/doc/mapping-dsl.md)
 
This document describes the declarative mapping rules used to project data from events or node outputs into LangGraph node state and Command(resume=...) payload.

## Goals
- General-purpose routing from sources (Event/Node/State) to targets (state.attributes|metadata|tool_input, resume.*).
- No/low-code: simple rules with optional transforms and conflict policies.
- Backward compatible with existing `qa_form`, `notification`, `human_text` behavior.

## Sources
- `event`: normalized event envelope with fields:
  - `event.type`: human_chat | a2a | webhook | timer | other
  - `event.source`: e.g., gui:<chatId>
  - `event.tag`: identifier to match checkpoint (e.g., metadata.i_tag)
  - `event.timestamp`: optional
  - `event.data`: payload incl. `human_text`, `qa_form_to_agent|qa_form`, `notification_to_agent|notification`, `metadata`
  - `event.context`: ids like `id`, `sessionId`, `chatId`, `msgId`
- `node`: current node output (optional usage)
- `state`: current state (read-only for rules)

## Targets
- `state.attributes.<path>`
- `state.metadata.<path>`
- `state.tool_input.<path>`
- `resume.<key>`

## Rule Schema
```
{
  "mappings": [
    {
      "from": ["event.data.qa_form_to_agent", "event.data.qa_form"],
      "to": [
        {"target": "state.attributes.forms.qa_form"},
        {"target": "resume.qa_form_to_agent"}
      ],
      "transform": null,
      "on_conflict": "merge_deep",
      "when": "event.type in ['human_chat','a2a']"
    }
  ],
  "options": {
    "strict": false,
    "default_on_missing": null,
    "apply_order": "top_down"
  }
}
```

- `from`: list of dot paths; first non-null value is used.
- `to`: one or more targets to write the value to.
- `transform` (optional): built-ins like `to_string`, `identity` (extensible later).
- `on_conflict`: overwrite | skip | merge_shallow | merge_deep | append.
- `when` (optional): simple expression with access to `event`, `node`, `state`.

## Defaults (preserve current behavior)
- Map QA form to `state.attributes.forms.qa_form` and `resume.qa_form_to_agent`.
- Map Notification to `state.attributes.notifications.latest` and `resume.notification_to_agent`.
- Map Human text to `state.attributes.human.last_message` and `resume.human_text`.
- Map `event.tag` to `state.attributes.cloud_task_id`. If checkpoint exists, it is also injected into checkpoint `values.attributes.cloud_task_id`.

## Where it runs
- Implemented in `agent/tasks_resume.py`:
  - `normalize_event()` builds the event envelope.
  - `select_checkpoint()` finds the checkpoint by tag.
  - `build_resume_from_mapping()` applies rules to produce `(resume_payload, state_patch)`.
  - `build_general_resume_payload()` orchestrates and injects cloud_task_id.
- `agent/tasks.py` uses this behind feature flag `RESUME_PAYLOAD_V2` (default on) and deep-merges `state_patch` into `task.metadata['state']`.

## Per-skill customization
- Skills can set `EC_Skill.mapping_rules` (a dict matching the schema). If absent, defaults apply.
- Example (see `agent/ec_skills/dev_utils/skill_dev_utils.py`):
```
{
  "mappings": [
    {
      "from": ["event.data.sample_tool_input"],
      "to": [ {"target": "state.tool_input.sample"}, {"target": "resume.sample_tool_input"} ],
      "on_conflict": "overwrite"
    },
    {
      "from": ["event.data.sample_meta"],
      "to": [ {"target": "state.metadata.extra"} ],
      "on_conflict": "merge_deep"
    }
  ]
}
```

## Future GUI (Node Editor)
- Source picker: Event / Node Output / State trees with path selection and previews.
- Target picker: attributes / metadata / tool_input / resume with path editor and validation.
- Transforms: dropdown with optional parameters.
- Conflict policy: radio selection.
- Conditions: simple rule builder.
- Preview: show computed writes given a sample input.

## Testing
- Unit tests in `tests/test_tasks_resume.py` cover normalization, mapping, checkpoint selection, and orchestration.
