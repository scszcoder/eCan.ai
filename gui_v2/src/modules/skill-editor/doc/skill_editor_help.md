# Skill Editor User Guide

Welcome to the Skill Editor. This guide explains the core features and how to use the canvas, nodes, the debugger, and test runs.

---

## Table of Contents

- [Introduction](#introduction)
- [Editor Basics](#editor-basics)

  - [Toolbar](#toolbar)
  - [Add/Remov/Edit/Duplicate Nodes](#addremoveditduplicate-nodes)
  - [Adding/Removing/Re-route Edges](#addingremovingre-route-edges)
  - [Multi-select](#multi-select)
  - [Panning & Zooming](#panning--zooming)
  - [Multi-Sheet (Naming Convention）](#multi-sheet-naming-convention)
  - [Saving & Loading](#saving--loading)
- [Cross-Sheet References](#cross-sheet-references)

  - [Define a sheet interface](#define-a-sheet-interface)
  - [Insert a Sheet Call](#insert-a-sheet-call)
  - [Map inputs and outputs](#map-inputs-and-outputs)
  - [Navigate between sheets](#navigate-between-sheets)
  - [Save/Load multi-sheet bundles](#saveload-multi-sheet-bundles)
  - [Troubleshooting](#troubleshooting)
- [Run And Debug](#run-and-debug)

  - [Breakpoints](#breakpoints)
  - [Controlled Run: Pause / Step / Resume / Stop](#controlled-run-pause--step--resume--stop)
- [Version Controll With Git](#version-controll-with-git)

  - [Git with eCan.ai's cloud service](#git-with-ecanais-cloud-service)
  - [Git locally](#git-locally)
- [Test Run](#test-run)

  - [Inputs](#inputs)
  - [Outputs](#outputs)
- [Shortcuts](#shortcuts)
- [Nodes](#nodes)

  - [Start/End](#startend)
  - [Code](#code)
  - [LLM](#llm)
  - [HTTP](#http)
  - [Condition / Loop / Group](#condition--loop--group)
  - [MCP Tool Call](#mcp-tool-call)
  - [Pend For Event](#pend-for-event)
- [Reference](#reference)
- [FAQ](#faq)

---

## Introduction

The Skill Editor lets you build flows by placing nodes on a canvas and connecting them. Each node performs a specific task (e.g., run code, call an LLM, request HTTP APIs). Use the sidebar to configure the selected node.

## Editor Basics

### Toolbar

- Add nodes, zoom, fit view, auto-layout, open/save, test-run controls, help.

### Add/Remov/Edit/Duplicate Nodes

- right click the mouse, or click on the node icon to bring up the node selection menu, pick the one you'd like to add the sheet, move the mouse to where you'd like to place the node on the sheet, click to drop the node to that location.
- use node menu on its upper right corner to remove the node.
- double-click on the node to bring up its node editor, and key in the relavent parameters and selection the various options associated with that node.
- use node menu on its upper right corner to make a copy of the node.

### Adding/Removing/Re-route Edges

- Click a node's output port, keep the mouse down and drag it to next node's input port to complete the edge adding process.
- Click and press down on an edge's end-point, drag it to any blank spot on the sheet to remove the edge.
- Click and press down on an edge's end-point, drag it to another node's input port to re-route the edge.

### Multi-select

- Hold down <shift> [shift] key on keyboard, then use mouse click drag and drop to draw a enclosing rectangle covering the nodes you'd like to multi-select, then you can move them all-together

### Panning & Zooming

- To pan around the canvas - hold down the mouse wheel button and move around, or alternatively move the view port in the minimap..
- To zoom in and out - hold down the <CTRL> key and scroll the mouse wheel.

### Multi-Sheet (Naming Convention）

- Use the sheet menu on upper right corner to add/remove additional sheet to your skill (work-flow) project, making a complicated flow more managable.
- Sheet name can be modified directly on the sheet tab, just double click on the sheet name on the tab, you can then edit the sheet name.
- Make sure the sheet that contains entry point node of the entire skill is named "main", this is crtical for running skill later on.
- Add a "sheet-call" node to a sheet if this sheet will be calling work flow on another sheet.

### Saving & Loading

- Save the current flow to JSON; load an existing flow from JSON.
- The directory to store skills are fixed, it will be $SKILL_ROOT/my_skills/
- If you use skill editor to create a skill, it will be stored under "diagram_dir" sub-dir in your skill directory. If you directly code up the skill, it will need to be stored under "code_dir" sub-dir in your skill directory.
- data mapping rule json file will be stored at the same level as "diagram_dir" and "code_dir".
- If you code up your skill (langgraph based workflow) and wish to be able to view the topology graphically, you will need to call the langgraph2flowgram() function to do the translation, once done, the "diagram_dir" and the flowgram files will be generated, in which case, you can load and run to debug graphically.

### Data Movements （between nodes & between external event and node）

- A workflow node will sometimes generate new data for other nodes to use, the carrier for the data exchange is the node state data structure. but since the node state data structure is generic, but every workflow is different, there needs to be a way to describe the data move scheme, and we use a simple mapping DSL (domain specific language) to manage this.
- Quite often a workflow involves external events, an example situation could be a human-in-loop action where we pend for human input and the human chat message arrived, or in a multi-agent screnario a workflow may pend on data from another agent and this data just arrived, or simply some type of timer based wait and wait expired or an incoming webhook callback event, when an event happens and trigger the workflow to resume, some data carried along with the event may need to injected back into the workflow (i.e. the node state), again there needs to be a way to describe/specify such data flow, and we use the same mapping DSL to describe this. the mapping DSL is json based, the details can be found [here](./mapping-dsl.md).

---

## Cross-Sheet References

Multi-sheet flows let you organize logic across multiple canvases (sheets). Use a `sheet-call` node to call another sheet that declares its inputs/outputs.

### Define a sheet interface

- Add a `sheet-inputs` node on the callee sheet and list the input names (e.g., `x`, `y`).
- Add a `sheet-outputs` node on the callee sheet and list the output names (e.g., `result`).
- You can edit these lists from the sidebar form when the node is selected.

### Insert a Sheet Call

- Open the caller sheet.
- Click the Sheets menu (layers icon) and choose `Insert Sheet Call…`.
- A `sheet-call` node appears; select it to open the sidebar form.
- Choose the target sheet from the dropdown.

### Map inputs and outputs

- For each exposed input, choose a mapping:
  - `Constant`: enter a JSON value (e.g., `42` or `{ "foo": "bar" }`).
  - `Local Port`: pick a node from the dropdown, then enter the port name.
- For each exposed output, map the result to a local port similarly.

### Navigate between sheets

- In the `sheet-call` panel, click `Jump to target sheet` to open the callee.

### Save/Load multi-sheet bundles

- Regular Save also writes a companion bundle file with `-bundle.json` suffix. This contains all sheets, open tabs, and the active sheet id.
- Use `Load Bundle…` from the Sheets menu to open a multi-sheet bundle.

### Troubleshooting

- Missing mappings: If any required input/output isn’t mapped, a warning appears in the sidebar and a `⚠` badge is appended to the `sheet-call` title.
- Missing target sheet: Ensure the `targetSheetId` exists; fix by selecting a valid target sheet.
- Cycles: If the call graph contains cycles, a warning is logged when loading the bundle. Consider refactoring to avoid recursive loops.
- Interfaces not detected: Make sure the callee contains `sheet-inputs` and `sheet-outputs` nodes with the desired names.

---

## Run And Debug

When run and debug a skill under-development, the skill will still be assigned to a task and to an agent to run, this 
task will be a special development task run by a tester agent. And if your workflow involves chat (which likely will 
always be the case), when chatting with the tester agent, be sure to always have "dev>" prefix in your chat message.
### Breakpoints

- Go to a node's upper right corner menu to toggle on/off a breakpoint on this node(will break at pre-execution instance). you can set multiple breakpoints on multiple node.

### Controlled Run: Pause / Step / Resume / Stop

- Use control buttons on the toolbar to manage execution during debugging, a running animation will be shown on the current running node, once stopped, you can open node editor to inspect the node state, and modify the node state if you like, and then continue to run.

## Version Controll With Git

### Git with eCan.ai's cloud service

- If you subscribe to eCan.ai's paid service, you may version control your skills on eCan.ai's git repository and potentially commercialized your skill.

### Git locally

- You can git version control your skill files locally.

---

## Test Run

### Inputs

- Provide input JSON or form values to simulate a run.

### Outputs

- Inspect outputs emitted by nodes and the final End node result.

---

## Shortcuts

- Ctrl/Cmd + Z: Undo
- Ctrl/Cmd + Y: Redo
- Mouse wheel: Zoom
-

---

## Nodes

### Start/End

Start emits initial values; End collects and displays final outputs.

### Code

- Edit code inline with Monaco editor.
- Language selector supports Python, JavaScript, and TypeScript.
- "Reset to template" restores a starter snippet for the selected language.
- "Load File" allows importing code from local files.

### LLM

- Choose a Model Provider and Model Name from dropdowns.
- Provider/Model options are loaded from a model store; defaults are used if none are provided.
- Note: as a good convention, LLM should always return structured data rather than pure string text, we should always ask LLM to return *{"message": "your message here", "meta_data": dict}* as this our standard LLM result post processing code assumes. This will make inter-node data passing so much easier.

### HTTP

- Configure method, URL, headers, params, body, timeout.
- API Key field is available for passing credentials.
- Standard post http API call handling will put result in node state's *http_response* field.

### Condition / Loop / Group

- Condition routes based on predicates.
- Loop iterates over arrays and runs nested blocks.
- Group organizes related nodes.

### MCP Tool Call

- This node will invoke a MCP tool call.
- Node state's tool_input field should be populated for tool call input.
- Raw mcp tool call always returns data in mcp's own TextContent data structure, it contains "*type*", "*text*", and "*meta*" , or alternatively *ImageContent* or *AudioContent* where "*data*" and "*mimeType*" are in place of "*text*", "*data*" is in base64-encoded string format
- Standard post tool call handling will put result in node state's tool_result field.

### Pend For Event

- This node generates an interrupt and break out of the workflow (critical to create i_tag field/attribute under interrupt object, in our case, this is automatically done using node name as the tag, however this doesn't have to be the case, you can tag it to anything you like),
- will resume until designated event occurs.
- Example: timer based wait (expiration event), human/agent in the loop (human/agent feedback received event), time consuming API calling(call back received event), pub/sub websocket (push message received event), web sse (server send event received event)
- Note: it is critical to have event orginator carry the i_tag, so that when event occurs, it carries the exact i_tag associated with the interrupted noded that's pending for this event, and we can therefore resume from where we were left off.

## Reference

- Mapping DSL (Node State & Resume Payload): see `mapping-dsl.md` in this folder or open directly: [Mapping DSL](./mapping-dsl.md)

---

## FAQ

- Why doesn’t my editor show? Try refreshing the page; ensure workers are loading correctly.
- How do I switch languages in Code nodes? Use the language dropdown above the editor.

---

Last updated: (add date)
