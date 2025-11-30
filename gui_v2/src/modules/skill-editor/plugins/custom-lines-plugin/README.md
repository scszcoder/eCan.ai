# Custom Lines Plugin - Phase 1 Investigation

## Goal
Investigate FlowGram.ai's plugin API to determine if we can customize edge routing without forking the library.

## Current Status
🔍 **Phase 1: Investigation & Prototyping**

### What We're Testing
1. Can we create a custom plugin that intercepts line events?
2. What hooks/lifecycle methods are available?
3. Can we access and modify line rendering?
4. Can we override the default FreeLinesPlugin behavior?

## Usage

### Enable the Plugin
In `use-editor-props.tsx`, replace or add alongside `createFreeLinesPlugin`:

```typescript
import { createCustomLinesPlugin } from '../plugins/custom-lines-plugin';

// In the plugins array:
plugins: () => [
  createCustomLinesPlugin({
    debug: true,
    enableLogging: true,
  }),
  // ... other plugins
]
```

### Check Console Logs
Open browser DevTools console and look for `[CustomLinesPlugin]` messages when:
- Creating connections between nodes
- Moving nodes (which updates lines)
- Deleting connections
- Loading a workflow

## Investigation Checklist

- [ ] Plugin initializes successfully
- [ ] Can intercept line creation events
- [ ] Can intercept line rendering
- [ ] Can access line data (from/to ports, waypoints, etc.)
- [ ] Can modify line appearance
- [ ] Can add custom line data/metadata
- [ ] Can override default line path calculation
- [ ] Can add interactive elements to lines

## Next Steps

Based on findings:
- **If hooks exist**: Implement orthogonal routing in the plugin
- **If limited API**: Try service override approach
- **If blocked**: Consider forking `@flowgram.ai/free-lines-plugin`

## Notes
- FlowGram uses dependency injection (InversifyJS-like)
- Lines are likely SVG paths rendered on canvas
- The `WorkflowLinesManager` service manages line state
