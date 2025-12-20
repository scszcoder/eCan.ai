# Mapping DSL (Domain-Specific Language) for Node State and Resume Payload

This document describes the declarative mapping rules used to project data from events or node outputs into LangGraph node state and Command(resume=...) payload.

## Overview

The mapping DSL system provides two levels of data mapping:

1. **Skill-Level Mapping**: Event-to-state mapping and event routing (configured in START node)
2. **Node-Level Mapping**: State-to-state transfer mapping (configured in individual nodes)

Both levels support run_mode separation (`developing` vs `released`) for different runtime behaviors.

## Goals

- General-purpose routing from sources (Event/Node/State) to targets (state.attributes|metadata|tool_input, resume.*).
- No/low-code: simple rules with optional transforms and conflict policies.
- Backward compatible with existing `qa_form`, `notification`, `human_text` behavior.
- Support both development (debug-friendly) and released (production-optimized) modes.
- Enable user-configurable event routing to tasks.

## Sources

- `event`: normalized event envelope with fields:
  - `event.type`: human_chat | a2a | webhook | timer | other
  - `event.source`: e.g., gui:<chatId>
  - `event.tag`: identifier to match checkpoint (e.g., metadata.i_tag)
  - `event.timestamp`: optional
  - `event.data`: payload incl. `human_text`, `qa_form_to_agent|qa_form`, `notification_to_agent|notification`, `metadata`
  - `event.context`: ids like `id`, `sessionId`, `chatId`, `msgId`
- [Deprecated] `node`: current node output (no longer used in node-level mappings)
- `state`: current state (read-only for rules)

## Targets

- `state.attributes.<path>`
- `state.metadata.<path>`
- `state.tool_input.<path>`
- `resume.<key>`

## data_mapping.json Structure

Skills save their mapping rules in `data_mapping.json` alongside the skill JSON file:

```json
{
  "developing": {
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
  },
  "released": {
    "mappings": [
      // Same as developing, but without debug metadata
    ],
    "options": {
      "strict": true,
      "default_on_missing": null,
      "apply_order": "top_down"
    }
  },
  "node_transfers": {
    "node_name_1": {
      "mappings": [
        {
          "from": ["node.result.api_response"],
          "to": [{"target": "state.tool_input.data"}],
          "transform": "parse_json"
        }
      ]
    }
  },
  "event_routing": {
    "human_chat": {
      "task_selector": "name_contains:chatter",
      "queue": "chat_queue"
    },
    "custom_event": {
      "task_selector": "id:specific_task_id",
      "queue": "custom_queue"
    }
  }
}
```

### Rule Schema Fields

- `from`: list of dot paths; first non-null value is used.
- `to`: one or more targets to write the value to.
- `transform` (optional): built-ins like `to_string`, `parse_json`, `pick`, `coalesce`, `identity`.
- `on_conflict`: overwrite | skip | merge_shallow | merge_deep | append.
- `when` (optional): simple expression with access to `event`, `node`, `state`.

## run_mode System

Skills have a `run_mode` field that controls which mapping set is used at runtime:

- **`developing`**: Debug-friendly mode

  - Includes debug metadata mappings
  - `strict: false` - lenient error handling
  - Preserves `event.data.metadata` for debugging
- **`released`**: Production-optimized mode

  - Minimal metadata only
  - `strict: true` - strict validation
  - Optimized for performance

The `run_mode` is controlled by the "Released" toggle button in the skill editor UI.

## Mapping Levels

### 1. Skill-Level Mapping (START Node)

Configured in the START node editor, applies to the entire skill:

- **Event-to-State Mapping**: Maps incoming events to state fields
- **Event Routing**: Routes events to appropriate task queues

Example use cases:

- Map chat messages to `state.attributes.human.last_message`
- Map QA forms to `state.attributes.forms.qa_form`
- Route `human_chat` events to chatter tasks

### 2. Node-Level Mapping (Other Nodes)

Configured in individual node editors, applies to state-to-state transfers:

- **State-to-State Transfer**: Maps values from the current state snapshot (which already contains preceding node outputs) into the current node's state fields
- Use `state.*` for both sources and targets

Example use cases:

- Map `node.result.api_response` to `state.tool_input.data`
- Transform JSON strings to objects with `parse_json`
- Extract specific fields with `pick` transform

## Defaults (preserve current behavior)

**Both developing and released modes include:**

- Map QA form to `state.attributes.forms.qa_form` and `resume.qa_form_to_agent`.
- Map Notification to `state.attributes.notifications.latest` and `resume.notification_to_agent`.
- Map Human text to `state.attributes.human.last_message` and `resume.human_text`.
- Map `event.tag` to `state.attributes.cloud_task_id`. If checkpoint exists, it is also injected into checkpoint `values.attributes.cloud_task_id`.

**Developing mode additionally includes:**

- Map `event.data.metadata` to `state.attributes.debug.last_event_metadata` for debugging.

## Where it runs

### Backend (Python)

**`agent/tasks_resume.py`:**

- `DEFAULT_MAPPINGS`: Separated by run_mode (`developing` / `released`)
- `load_mapping_for_task()`: Resolves mapping rules with precedence:
  1. Node-level mapping (from `skill.config.nodes[node_name].mapping_rules`)
  2. Skill-level mapping (from `skill.mapping_rules[run_mode]`)
  3. Defaults (from `DEFAULT_MAPPINGS[run_mode]`)
- `normalize_event()`: Builds the event envelope
- `select_checkpoint()`: Finds the checkpoint by tag
- `build_resume_from_mapping()`: Applies rules to produce `(resume_payload, state_patch)`
- `build_general_resume_payload()`: Orchestrates and injects cloud_task_id

**`agent/tasks.py`:**

- `launch_unified_run()`: Unified task execution supporting all trigger types
  - Replaces `launch_scheduled_run()`, `launch_reacted_run()`, `launch_interacted_run()`
  - Consistent interrupt-resume behavior across all modes
  - Uses mapping DSL via `_build_resume_payload()`
- Uses feature flag `RESUME_PAYLOAD_V2` (default on) and deep-merges `state_patch` into `task.metadata['state']`

**`agent/ec_skills/build_agent_skills.py`:**

- `load_from_code()`: Loads `data_mapping.json` from skill root
- `load_from_diagram()`: Loads `data_mapping.json` and `run_mode` from skill JSON
- Assigns to `skill.mapping_rules` for runtime use

### Frontend (TypeScript/React)

**Skill Editor Components:**

1. **`components/mapping/SkillLevelMappingEditor.tsx`** (NEW)

   - Edits skill-level mappings for START node
   - Separate sections for developing/released modes
   - Event routing configuration UI
2. **`components/mapping/MappingEditor.tsx`**

   - Edits node-to-node transfer mappings
   - Used for all non-START nodes
   - Preview functionality for testing rules
3. **`components/sidebar/sidebar-node-renderer.tsx`**

   - Detects START node vs other nodes
   - Shows appropriate mapping editor
   - Persists to `skillInfo.config.skill_mapping` (START) or `node.data.mapping_rules` (others)
4. **`components/tools/save.tsx`**

   - Extracts skill-level mappings from START node
   - Extracts node-level mappings from other nodes
   - Generates and saves `data_mapping.json` alongside skill JSON
5. **`components/tools/readonly.tsx`**

   - Released toggle button controls `run_mode`
   - Updates both UI `mode` and backend `run_mode`

## Per-skill customization

Skills can customize mapping rules in two ways:

### 1. Via GUI (Recommended)

**For Skill-Level Mappings:**

1. Open the START node in the skill editor
2. Scroll to "Skill-Level Mapping Rules" section
3. Configure mappings for both developing and released modes
4. Add event routing rules as needed
5. Save the skill

**For Node-Level Mappings:**

1. Open any non-START node in the skill editor
2. Scroll to "Node Transfer Mapping" section
3. Configure mappings from preceding node to current node
4. Use `node.*` paths for source, `state.*` paths for target
5. Save the skill

### 2. Via Code (Advanced)

Skills can set `EC_Skill.mapping_rules` programmatically:

```python
# In your skill's abc_skill.py
skill = EC_Skill(name="My Custom Skill")
skill.run_mode = "developing"  # or "released"
skill.mapping_rules = {
    "developing": {
        "mappings": [
            {
                "from": ["event.data.sample_tool_input"],
                "to": [
                    {"target": "state.tool_input.sample"},
                    {"target": "resume.sample_tool_input"}
                ],
                "on_conflict": "overwrite"
            }
        ],
        "options": {"strict": False}
    },
    "released": {
        "mappings": [...],
        "options": {"strict": True}
    },
    "event_routing": {
        "custom_event": {
            "task_selector": "name_contains:my_task",
            "queue": "custom_queue"
        }
    }
}
```

## GUI Features (Implemented)

✅ **START Node Editor:**

- Skill-level mapping configuration
- Separate sections for developing/released modes
- Event routing configuration
- Collapsible panels for organization

✅ **Other Node Editors:**

- Node-to-node transfer mapping
- Clear labels distinguishing from skill-level mapping
- Help text explaining source/target paths

✅ **Mapping Editor Component:**

- JSON-based rule editing
- Preview functionality
- Transform selection
- Conflict policy selection

✅ **Released Toggle:**

- Controls both UI mode and backend run_mode
- Visual feedback (lock/unlock icon)
- Toast notifications on mode change

## File Structure

When you save a skill, the following files are created:

```
my_skill_skill/
├── data_mapping.json                 # Mapping rules (at skill root level)
├── diagram_dir/
│   ├── my_skill_skill.json          # Main skill JSON with workFlow
│   └── my_skill_skill_bundle.json   # Multi-sheet bundle
└── code_skill/                       # Optional Python code
    └── ...
```

The `data_mapping.json` file contains:

- Skill-level mappings (from START node)
- Node-level mappings (from other nodes)
- Event routing rules
- Separated by run_mode (developing/released)

## Examples

### Example 1: Skill-Level Event Mapping

Map incoming chat messages to state:

```json
{
  "developing": {
    "mappings": [
      {
        "from": ["event.data.human_text"],
        "to": [
          {"target": "state.attributes.human.last_message"},
          {"target": "resume.human_text"}
        ],
        "transform": "to_string",
        "on_conflict": "overwrite"
      }
    ]
  }
}
```

### Example 2: Node-Level State-to-State Transfer

Map API response (already present in state) into current node's tool_input:

```json
{
  "mappings": [
    {
      "from": ["state.result.api_response"],
      "to": [{"target": "state.tool_input.data"}],
      "transform": "parse_json",
      "on_conflict": "overwrite"
    }
  ]
}
```

### Example 3: Event Routing

Route different event types to appropriate tasks:

```json
{
  "event_routing": {
    "human_chat": {
      "task_selector": "name_contains:chatter",
      "queue": "chat_queue"
    },
    "scheduled_report": {
      "task_selector": "name_contains:reporter",
      "queue": null
    }
  }
}
```

## Testing

### Unit Tests

- `tests/test_tasks_resume.py`: Covers normalization, mapping, checkpoint selection, and orchestration

### Manual Testing Checklist

1. **Skill Creation:**

   - [ ]  Create new skill in editor
   - [ ]  Open START node, add skill-level mappings
   - [ ]  Open other nodes, add node-to-node mappings
   - [ ]  Toggle released mode
   - [ ]  Save and verify `data_mapping.json` is created
2. **Skill Loading:**

   - [ ]  Load saved skill
   - [ ]  Verify mappings appear in START node editor
   - [ ]  Verify mappings appear in other node editors
   - [ ]  Verify run_mode matches released toggle
3. **Runtime:**

   - [ ]  Run skill in developing mode
   - [ ]  Run skill in released mode
   - [ ]  Verify correct mappings are used
   - [ ]  Test interrupt-resume with scheduled tasks
4. **Unified Launch:**

   - [ ]  Test scheduled task execution
   - [ ]  Test a2a message handling
   - [ ]  Test chat message handling
   - [ ]  Verify consistent behavior across all modes

## Migration Guide

### For Existing Skills

Existing skills without `data_mapping.json` will continue to work using default mappings. To add custom mappings:

1. Open the skill in the editor
2. Configure mappings in START node (skill-level)
3. Configure mappings in other nodes (node-to-node)
4. Save the skill - `data_mapping.json` will be created automatically

### For Code-Based Skills

If your skill sets `mapping_rules` programmatically, update the structure:

**Old format:**

```python
skill.mapping_rules = {
    "mappings": [...],
    "options": {...}
}
```

**New format:**

```python
dskill.mapping_rules = {
    "developing": {
        "mappings": [...],
        "options": {"strict": False}
    },
    "released": {
        "mappings": [...],
        "options": {"strict": True}
    }
}
```

The old format is still supported for backward compatibility, but will use the same mappings for both modes.

## Troubleshooting

**Mappings not being applied:**

- Check that `data_mapping.json` exists alongside skill JSON
- Verify `run_mode` is set correctly in skill JSON
- Check logs for mapping load errors in `build_agent_skills.py`

**Wrong mappings being used:**

- Verify the released toggle matches your intended run_mode
- Check mapping precedence: Node-level → Skill-level → Defaults
- Use `logger.debug` to trace `load_mapping_for_task()` resolution

**Scheduled tasks not resuming:**

- Ensure you're using `launch_unified_run()` (old functions are deprecated)
- Check that interrupt-resume payload is being built correctly
- Verify checkpoint is being saved and retrieved

## References

- **Backend Implementation:** `agent/tasks_resume.py`, `agent/tasks.py`, `agent/ec_skills/build_agent_skills.py`
- **Frontend Implementation:** `gui_v2/src/modules/skill-editor/components/mapping/`, `gui_v2/src/modules/skill-editor/components/sidebar/`
- **Example Skill:** `agent/ec_skills/dev_utils/skill_dev_utils.py`
