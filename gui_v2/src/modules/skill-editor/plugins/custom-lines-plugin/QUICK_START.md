# Quick Start Guide - Phase 1 Testing

## 🚀 Start Testing in 3 Steps

### 1. Run the Dev Server
```bash
cd gui_v2
npm run dev
```

### 2. Open Browser DevTools
- Press **F12** (or Cmd+Option+I on Mac)
- Go to **Console** tab
- Look for `[CustomLinesPlugin]` messages

### 3. Test Line Operations
Try these actions and watch the console:

#### ✅ Create a Connection
1. Drag from a node's output port (right side)
2. Drop on another node's input port (left side)
3. **Expected:** See `🎉 onLineCreate called` in console

#### ✅ Move a Node
1. Drag a node that has connections
2. **Expected:** See `🔄 onLineUpdate called` (if hook exists)

#### ✅ Delete a Connection
1. Click on a connection line to select it
2. Press **Delete** or **Backspace**
3. **Expected:** See `🗑️ onLineDelete called`

## 🔍 Debug Commands

Open browser console and try these:

```javascript
// Inspect the plugin context
window.__CUSTOM_LINES_DEBUG__.inspectContext()

// Get raw context object
window.__CUSTOM_LINES_DEBUG__.getContext()

// Check available services
window.__SE_DUMP_ANCHORS__?.()
```

## 📊 What to Look For

### ✅ Success Signs
- Plugin initializes: `✅ onInit called`
- Found services: `✅ Found linesManager`
- Hooks are called: `🎉 onLineCreate called`

### ❌ Warning Signs
- No initialization logs
- `❌ linesManager not found`
- No hooks called when creating lines
- TypeScript/JavaScript errors

## 📝 Quick Checklist

Copy this to track your findings:

```
[ ] Plugin loads successfully
[ ] onInit hook works
[ ] Can access linesManager service
[ ] Can access document service
[ ] onLineCreate hook works
[ ] onLineUpdate hook works
[ ] onLineDelete hook works
[ ] onLineRender hook works
[ ] Can see line data structure
[ ] Can see line methods
```

## 🎯 Next Actions

Based on what you see:

### If Most Hooks Work ✅
→ **Great!** Proceed to implement orthogonal routing
→ See `PHASE2_PLAN.md` (to be created)

### If Some Hooks Work ⚠️
→ Document which ones work
→ Try alternative approaches (service override)

### If No Hooks Work ❌
→ We'll need to fork the library
→ See `FORK_STRATEGY.md` (to be created)

## 🐛 Troubleshooting

### Plugin Not Loading?
- Check for TypeScript errors in terminal
- Verify import in `use-editor-props.tsx`
- Check browser console for errors

### No Logs Appearing?
- Make sure `enableLogging: true` in plugin options
- Check console filter (should show all logs)
- Try refreshing the page

### Hooks Not Called?
- This is expected - we're discovering the API
- Document which hooks don't work
- This tells us what approach to take next

## 📞 Need Help?

1. Check `TESTING.md` for detailed scenarios
2. Review `PHASE1_SUMMARY.md` for context
3. Check FlowGram.ai GitHub issues
4. Document your findings in the README

## ⏱️ Time Estimate

- **Setup & First Test:** 5-10 minutes
- **Full Investigation:** 1-2 hours
- **Documentation:** 30 minutes

**Total:** ~2-3 hours for complete Phase 1

---

**Ready?** Start the dev server and let's see what we discover! 🚀
