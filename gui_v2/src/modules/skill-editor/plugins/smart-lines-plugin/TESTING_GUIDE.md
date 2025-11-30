# Smart Lines Plugin - Testing Guide

## Phase 2A Complete ✅

We've implemented the core routing algorithm with A* pathfinding. Now we need to test it and integrate with FlowGram's line rendering.

## Quick Test

### 1. Refresh Browser
The plugin is now loaded. Check console for:
```
[SmartLinesPlugin] ✅ Smart Lines Plugin initialized
[SmartLinesPlugin] ✅ Found document service: ...
[SmartLinesPlugin] 💡 Smart routing functions exposed: window.__SMART_LINES__
```

### 2. Test Pathfinding Algorithm

Open browser console and try:

```javascript
// Test 1: Simple path with no obstacles
const result1 = window.__SMART_LINES__.calculatePath(
  { x: 0, y: 0 },
  { x: 500, y: 500 },
  []
);
console.log('Simple path:', result1);

// Test 2: Path with one obstacle
const result2 = window.__SMART_LINES__.calculatePath(
  { x: 100, y: 100 },
  { x: 500, y: 500 },
  [
    { x: 250, y: 250, width: 200, height: 100 }
  ]
);
console.log('Path avoiding one node:', result2);

// Test 3: Path with multiple obstacles
const result3 = window.__SMART_LINES__.calculatePath(
  { x: 50, y: 50 },
  { x: 600, y: 400 },
  [
    { x: 150, y: 100, width: 150, height: 80 },
    { x: 350, y: 200, width: 150, height: 80 },
    { x: 250, y: 300, width: 150, height: 80 },
  ]
);
console.log('Path avoiding multiple nodes:', result3);

// Test 4: Get current nodes in the editor
const nodes = window.__SMART_LINES__.getNodeBounds();
console.log('Current nodes:', nodes);

// Test 5: Calculate path between actual nodes
if (nodes.length >= 2) {
  const from = { x: nodes[0].x + nodes[0].width, y: nodes[0].y + nodes[0].height / 2 };
  const to = { x: nodes[1].x, y: nodes[1].y + nodes[1].height / 2 };
  const obstacles = nodes.slice(2); // Use other nodes as obstacles
  
  const result = window.__SMART_LINES__.calculatePath(from, to, obstacles);
  console.log('Path between actual nodes:', result);
  console.log('SVG path:', result.svg);
}
```

## Expected Results

### Success Indicators ✅
- Path avoids all obstacles
- Uses orthogonal (H-V) segments
- Simplified path has minimal points
- SVG path string is generated
- No errors in console

### What to Check
1. **Path Quality**
   - Does it go around nodes?
   - Are segments orthogonal (horizontal/vertical)?
   - Is the path reasonably short?

2. **Performance**
   - Check timing in console logs
   - Should be <100ms for most paths

3. **Edge Cases**
   - What if start/end is inside an obstacle?
   - What if no path exists?
   - What if obstacles overlap?

## Visualization

To visualize the calculated paths, you can:

1. **Copy SVG Path**
   ```javascript
   const result = window.__SMART_LINES__.calculatePath(...);
   console.log(result.svg);
   // Copy this and paste into an SVG editor or HTML
   ```

2. **Create Test HTML**
   ```html
   <svg width="800" height="600" style="border: 1px solid black;">
     <!-- Paste obstacles -->
     <rect x="250" y="250" width="200" height="100" fill="lightblue" />
     
     <!-- Paste calculated path -->
     <path d="M 100 100 L ..." stroke="red" stroke-width="2" fill="none" />
   </svg>
   ```

## Next Steps - Phase 2B

Now that the algorithm works, we need to integrate it with FlowGram's line rendering:

### Option 1: Override Line Path Calculation (Preferred)
Find where FlowGram calculates line paths and override it.

**Investigation needed:**
```javascript
// In console, check:
const ctx = window.__CUSTOM_LINES_DEBUG__.ctx;
const document = ctx.document;

// Look for line-related methods
Object.getOwnPropertyNames(Object.getPrototypeOf(document))
  .filter(m => m.toLowerCase().includes('line'));

// Check if there's a lines manager
const linesManager = ctx.linesManager;
if (linesManager) {
  console.log('Lines manager methods:', 
    Object.getOwnPropertyNames(Object.getPrototypeOf(linesManager))
  );
}
```

### Option 2: Create Custom Line Renderer
If we can't override path calculation, create a custom line renderer component.

### Option 3: Monkey-Patch (Last Resort)
Intercept and modify line entities after creation.

## Debugging

### Enable Detailed Logging
The plugin already has debug mode enabled. Check console for:
- `📐 Calculated path:` - Shows path calculation details
- `⚠️` warnings - Indicates issues
- `✅` success - Confirms operations

### Common Issues

**Issue: No path found**
- Check if obstacles are blocking all routes
- Try reducing `nodePadding`
- Check if start/end points are valid

**Issue: Path crosses nodes**
- Verify obstacle rectangles are correct
- Check `nodePadding` value
- Ensure grid size is appropriate

**Issue: Performance slow**
- Reduce `gridSize` (larger cells = faster)
- Simplify obstacle list
- Check for very large canvases

## Performance Benchmarks

Run this to test performance:

```javascript
const nodes = [
  { x: 100, y: 100, width: 150, height: 80 },
  { x: 300, y: 200, width: 150, height: 80 },
  { x: 500, y: 100, width: 150, height: 80 },
  { x: 200, y: 300, width: 150, height: 80 },
  { x: 400, y: 350, width: 150, height: 80 },
];

console.time('pathfinding');
for (let i = 0; i < 100; i++) {
  window.__SMART_LINES__.calculatePath(
    { x: 50, y: 50 },
    { x: 700, y: 500 },
    nodes
  );
}
console.timeEnd('pathfinding');
// Should be < 5000ms for 100 iterations
```

## Success Criteria

- [ ] Plugin loads without errors
- [ ] Can calculate paths via console
- [ ] Paths avoid all obstacles
- [ ] Paths use orthogonal routing
- [ ] Performance is acceptable (<100ms per path)
- [ ] Works with actual node positions

## Current Status

✅ **Phase 2A Complete** - Algorithm implemented and testable  
🔄 **Phase 2B Next** - Integrate with FlowGram line rendering  
⏳ **Phase 2C Pending** - Full integration and testing  
⏳ **Phase 2D Pending** - Polish and optimization  

## Questions to Answer

1. How does FlowGram calculate line paths?
2. Where can we override the path calculation?
3. Can we access line entities before rendering?
4. What's the line update lifecycle?

Test the algorithm now and report findings!
