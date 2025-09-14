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
