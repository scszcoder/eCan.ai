# Phase 1 Findings - Custom Lines Plugin

## Error Encountered

### Issue 1: Plugin Structure ✅ FIXED
**Error:** `plugin.initPlugin is not a function`

**Cause:** Plugin was returning a plain object instead of using `definePluginCreator`

**Fix:** Updated to use FlowGram's plugin API:
```typescript
export const createCustomLinesPlugin: PluginCreator<CustomLinesPluginOptions> = 
  definePluginCreator<CustomLinesPluginOptions, FreeLayoutPluginContext>({
    onInit(ctx, options) { ... }
  });
```

### Issue 2: Service Binding Error ⚠️ IN PROGRESS
**Error:** `No matching bindings found for serviceIdentifier: WorkflowHoverService`

**Observation:**
- Error occurs when custom plugin loads BEFORE FreeLinesPlugin
- FreeLinesPlugin likely registers required services
- Plugin order matters in FlowGram

**Current Fix:** Load custom plugin AFTER FreeLinesPlugin
```typescript
plugins: () => [
  createFreeLinesPlugin({ ... }),  // Load first
  createCustomLinesPlugin({ ... }), // Load after
  // ... other plugins
]
```

**Status:** Testing if this resolves the issue

## Plugin API Discoveries

### Confirmed Plugin Structure
- Uses `definePluginCreator` from `@flowgram.ai/free-layout-editor`
- Type: `PluginCreator<Options>`
- Context: `FreeLayoutPluginContext`

### Confirmed Lifecycle Hooks
- ✅ `onInit(ctx, options)` - Plugin initialization
- ✅ `onDispose(ctx)` - Plugin cleanup

### Unknown/Unconfirmed Hooks
- ❓ `onLineCreate` - Not yet confirmed
- ❓ `onLineUpdate` - Not yet confirmed
- ❓ `onLineDelete` - Not yet confirmed
- ❓ `onLineRender` - Not yet confirmed

## Next Steps

1. **Test with corrected plugin order**
   - Refresh browser
   - Check if WorkflowHoverService error is resolved
   - Look for `[CustomLinesPlugin] ✅ Plugin initialized` in console

2. **Investigate available services**
   - Check what's in the context
   - Look for lines-related services
   - Document available methods

3. **Determine line customization approach**
   - If services available → Use service override
   - If hooks available → Use plugin hooks
   - If neither → Need to fork library

## User Observations

### Current Line Behavior (Non-Curved Mode)
- ❌ Lines are horizontal only (no vertical segments)
- ❌ Lines cross through nodes instead of going around them
- ❌ Cannot drag individual line segments
- ❌ Line is treated as a single entity
- ❌ No intelligent routing algorithm

### Required Behavior
✅ **Primary Requirement:** Lines should NEVER cross nodes - must route around them
✅ **Secondary:** Support orthogonal routing (H-V-H segments)
✅ **Nice to have:** Manual segment editing

## Questions to Answer

- [ ] What services are available in the plugin context?
- [ ] Is there a WorkflowLinesManager service?
- [ ] Can we access line data through services?
- [ ] Can we override line rendering?
- [ ] What does FreeLinesPlugin actually do?

## Logs to Watch For

After refresh, look for:
```
[CustomLinesPlugin] ✅ Plugin initialized
[CustomLinesPlugin] Context type: ...
[CustomLinesPlugin] Available properties: ...
[CustomLinesPlugin] ✅ Found linesManager: ...
[CustomLinesPlugin] ✅ Found document service: ...
[CustomLinesPlugin] 💡 Debug functions exposed: window.__CUSTOM_LINES_DEBUG__
```

## Debug Commands

Once loaded, try in browser console:
```javascript
// Inspect context
window.__CUSTOM_LINES_DEBUG__.inspectContext()

// Get context
window.__CUSTOM_LINES_DEBUG__.ctx

// Check for lines manager
window.__CUSTOM_LINES_DEBUG__.ctx.document
window.__CUSTOM_LINES_DEBUG__.ctx.playground
```
