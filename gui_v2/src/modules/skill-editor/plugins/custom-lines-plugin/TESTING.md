# Testing Guide - Custom Lines Plugin Phase 1

## Setup

1. **Start the dev server**
   ```bash
   cd gui_v2
   npm run dev
   ```

2. **Open the skill editor**
   - Navigate to the skill editor page
   - Open browser DevTools (F12)
   - Go to the Console tab

3. **Look for initialization logs**
   You should see:
   ```
   [CustomLinesPlugin] Plugin created with options: {...}
   [CustomLinesPlugin] onInit called {...}
   ```

## Test Scenarios

### Test 1: Plugin Initialization ✓
**Action:** Just load the editor  
**Expected:** See initialization logs in console  
**What to check:**
- Does `onInit` get called?
- What services are available in the context?
- Can we access `linesManager`?

### Test 2: Line Creation
**Action:** 
1. Drag from one node's output port
2. Connect to another node's input port

**Expected:** See logs like:
```
[CustomLinesPlugin] onLineCreate called {...}
```

**What to check:**
- Line ID
- From/To port information
- Line data structure
- Available properties

### Test 3: Line Updates
**Action:**
1. Create a connection
2. Move one of the connected nodes

**Expected:** See logs for line updates

**What to check:**
- Does `onLineUpdate` get called?
- What data changes?

### Test 4: Line Deletion
**Action:**
1. Select a connection (click on it)
2. Press Delete or Backspace

**Expected:** See deletion logs

**What to check:**
- Does `onLineDelete` get called?
- Can we intercept/prevent deletion?

### Test 5: Line Rendering
**Action:** Any line operation (create, update, move nodes)

**Expected:** See rendering logs

**What to check:**
- Does `onLineRender` get called?
- Can we modify the render output?
- What rendering data is available?

## Investigation Checklist

Fill this out as you test:

```
Plugin Lifecycle:
[ ] onInit - called on plugin initialization
[ ] onDispose - called on plugin cleanup
[ ] onContentChange - called when content changes

Line Events (if they exist):
[ ] onLineCreate - called when line is created
[ ] onLineUpdate - called when line is updated  
[ ] onLineDelete - called when line is deleted
[ ] onLineRender - called during line rendering
[ ] onLineSelect - called when line is selected
[ ] onLineHover - called when line is hovered

Services Available:
[ ] linesManager - manages line state
[ ] document - workflow document
[ ] playground - canvas/viewport
[ ] commandService - command execution

Line Data Structure:
[ ] id - unique identifier
[ ] from - source port/node
[ ] to - target port/node
[ ] data - custom data storage
[ ] path - SVG path or coordinates
[ ] waypoints - intermediate points
```

## Debug Commands

Add these to browser console for manual testing:

```javascript
// Check if plugin is loaded
window.__SE_DEBUG_ANCHORS__ = true;

// Dump available services
window.__SE_DUMP_ANCHORS__?.();

// Check command availability
window.__SE_CHECK_COMMANDS__?.();
```

## Expected Outcomes

### Best Case Scenario ✅
- Plugin hooks exist for line lifecycle
- We can access and modify line data
- We can override rendering
- **Next:** Implement orthogonal routing in the plugin

### Medium Case Scenario ⚠️
- Limited hooks, but can access services
- Need to use service override approach
- **Next:** Create custom WorkflowLinesManager

### Worst Case Scenario ❌
- No plugin hooks for lines
- Can't access line rendering
- **Next:** Fork `@flowgram.ai/free-lines-plugin`

## Logging Output Examples

Save interesting log outputs here for reference:

```
// Add your findings here as you test
```

## Next Steps

Based on test results, update the main README with:
1. What hooks are actually available
2. What data structures we can access
3. Recommended implementation approach
4. Any blockers or limitations found
