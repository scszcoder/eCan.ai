# Skill Editor User Guide

Welcome to the Skill Editor. This guide explains the core features and how to use the canvas, nodes, the debugger, and test runs.

---

## Table of Contents

- [Introduction](#introduction)
- [Nodes](#nodes)
  - [Start/End](#startend)
  - [Code](#code)
  - [LLM](#llm)
  - [HTTP](#http)
  - [Condition / Loop / Group](#condition--loop--group)
- [Editor Basics](#editor-basics)
  - [Toolbar](#toolbar)
  - [Selection & Sidebar](#selection--sidebar)
  - [Saving & Loading](#saving--loading)
  - [Panning & Zooming](#panning--zooming)
- [Debugger](#debugger)
  - [Breakpoints](#breakpoints)
  - [Controls: Pause / Step / Resume / Stop](#controls-pause--step--resume--stop)
- [Test Run](#test-run)
  - [Inputs](#inputs)
  - [Outputs](#outputs)
- [Shortcuts](#shortcuts)
- [FAQ](#faq)

---

## Introduction

The Skill Editor lets you build flows by placing nodes on a canvas and connecting them. Each node performs a specific task (e.g., run code, call an LLM, request HTTP APIs). Use the sidebar to configure the selected node.

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

### HTTP
- Configure method, URL, headers, params, body, timeout.
- API Key field is available for passing credentials.

### Condition / Loop / Group
- Condition routes based on predicates.
- Loop iterates over arrays and runs nested blocks.
- Group organizes related nodes.

---

## Editor Basics

### Toolbar
- Add nodes, zoom, fit view, auto-layout, open/save, test-run controls, help.

### Selection & Sidebar
- Click a node to open its editor in the sidebar. Multi-select hides the sidebar.

### Saving & Loading
- Save the current flow to JSON; load an existing flow from JSON.

### Panning & Zooming
- To pan around the canvas - hold down the mouse wheel button and move around, or alternatively move the view port in the minimap..
- To zoom in and out - hold down the <CTRL> key and scroll the mouse wheel.
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

## Debugger

### Breakpoints
- Toggle breakpoints on nodes and resume execution from paused states.

### Controls: Pause / Step / Resume / Stop
- Use control buttons on the toolbar to manage execution during development.

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

---

## FAQ

- Why doesn’t my editor show? Try refreshing the page; ensure workers are loading correctly.
- How do I switch languages in Code nodes? Use the language dropdown above the editor.

---

Last updated: (add date)
