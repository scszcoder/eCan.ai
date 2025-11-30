# Phase 1 Summary - Custom Lines Plugin Investigation

## What We've Built

### 1. Plugin Structure ✅
Created a minimal custom lines plugin at:
```
gui_v2/src/modules/skill-editor/plugins/custom-lines-plugin/
├── index.ts           # Main plugin implementation
├── types.ts           # Type definitions
├── README.md          # Documentation
├── TESTING.md         # Testing guide
└── PHASE1_SUMMARY.md  # This file
```

### 2. Plugin Integration ✅
- Added plugin export to `plugins/index.ts`
- Integrated into `use-editor-props.tsx` alongside `FreeLinesPlugin`
- Enabled debug logging to console

### 3. Investigation Hooks ✅
The plugin attempts to intercept:
- `onInit` - Plugin initialization
- `onDispose` - Plugin cleanup
- `onLineCreate` - Line creation events
- `onLineUpdate` - Line update events
- `onLineDelete` - Line deletion events
- `onLineRender` - Line rendering events
- `onContentChange` - Content change events

## How to Test

### Quick Start
1. **Run the dev server:**
   ```bash
   cd gui_v2
   npm run dev
   ```

2. **Open browser DevTools** (F12) and go to Console tab

3. **Look for logs:**
   - `[CustomLinesPlugin]` messages on page load
   - More logs when creating/editing connections

4. **Test scenarios:**
   - Create a connection between two nodes
   - Move a node (updates connected lines)
   - Delete a connection
   - Load a saved workflow

### What to Look For

**Success Indicators:**
- ✅ Plugin initializes (see init logs)
- ✅ Hooks are called (see event logs)
- ✅ Can access line data
- ✅ Can access services (linesManager, document, etc.)

**Red Flags:**
- ❌ No logs appear (plugin not loading)
- ❌ TypeScript errors (API mismatch)
- ❌ Hooks never called (API doesn't support them)
- ❌ Can't access line data

## Expected Findings

### Scenario A: Full Plugin API Support 🎉
**If we see:**
- All hooks being called
- Access to line data and services
- Ability to modify line properties

**Then:**
- ✅ We can implement custom routing in the plugin
- ✅ No need to fork the library
- **Next:** Phase 2 - Implement orthogonal routing

### Scenario B: Partial API Support 🤔
**If we see:**
- Some hooks work, others don't
- Limited access to line internals
- Can read but not modify

**Then:**
- ⚠️ Need to use service override approach
- ⚠️ May need to extend/wrap existing services
- **Next:** Investigate service injection approach

### Scenario C: No Plugin API for Lines ❌
**If we see:**
- No hooks called for line events
- Can't access line data
- Plugin only gets generic events

**Then:**
- ❌ Plugin approach won't work
- ❌ Need to fork `@flowgram.ai/free-lines-plugin`
- **Next:** Fork and modify the library

## Key Questions to Answer

1. **Plugin Lifecycle**
   - [ ] Does `onInit` get called?
   - [ ] What's in the context object?
   - [ ] Can we access services?

2. **Line Events**
   - [ ] Which hooks actually exist?
   - [ ] What data is passed to each hook?
   - [ ] Can we modify line properties?

3. **Line Data Structure**
   - [ ] What properties does a line have?
   - [ ] Where is the path/waypoint data stored?
   - [ ] Can we add custom metadata?

4. **Rendering Control**
   - [ ] Can we intercept rendering?
   - [ ] Can we provide custom SVG paths?
   - [ ] Can we add interactive elements?

5. **Service Access**
   - [ ] Can we get `WorkflowLinesManager`?
   - [ ] What methods does it expose?
   - [ ] Can we override/extend it?

## Documentation to Update

After testing, update these files with findings:

1. **README.md**
   - Add "Findings" section
   - Document available hooks
   - Update feasibility assessment

2. **TESTING.md**
   - Check off what works
   - Add example log outputs
   - Document any workarounds

3. **types.ts**
   - Refine type definitions based on actual structures
   - Add discovered interfaces
   - Remove incorrect assumptions

## Next Steps Decision Tree

```
Test Plugin
    │
    ├─ Hooks Work? ──YES──> Phase 2: Implement Routing
    │                       - Add orthogonal algorithm
    │                       - Add waypoint support
    │                       - Add interactive editing
    │
    ├─ Partial? ──────────> Alternative Approach
    │                       - Try service override
    │                       - Wrap existing services
    │                       - Custom renderer
    │
    └─ No Hooks? ──────────> Fork Library
                            - Clone free-lines-plugin
                            - Modify source
                            - Publish as custom package
```

## Timeline

- **Phase 1 (Current):** 1-2 days
  - Build plugin ✅
  - Test and investigate 🔄
  - Document findings ⏳

- **Phase 2:** 5-7 days
  - Implement routing algorithm
  - Add waypoint system
  - Interactive editing

- **Phase 3:** 3-4 days
  - Polish and optimize
  - Testing and bug fixes
  - Documentation

**Total Estimated:** 10-14 days

## Contact & Support

If you encounter issues:
1. Check browser console for errors
2. Verify plugin is loaded (see init logs)
3. Try disabling other plugins to isolate issues
4. Check FlowGram.ai GitHub issues for similar problems

## Resources

- FlowGram.ai Docs: https://flowgram.ai/
- GitHub Repo: https://github.com/bytedance/flowgram.ai
- Plugin Architecture: (to be documented based on findings)
