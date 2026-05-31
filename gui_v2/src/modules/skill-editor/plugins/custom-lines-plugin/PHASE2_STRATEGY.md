# Phase 2 Strategy - Implementing Node-Avoiding Routing

## Problem Statement

FlowGram's default line routing:
- Uses simple straight/horizontal lines
- **Does NOT avoid node overlaps** ❌
- No orthogonal (H-V-H) routing
- No manual segment editing

## Primary Goal

**Implement intelligent routing that NEVER crosses nodes**

## Approach Options

### Option A: Fork `@flowgram.ai/free-lines-plugin` ⭐ RECOMMENDED
**Feasibility:** HIGH  
**Effort:** Medium (3-5 days)  
**Control:** Full control over routing

**Steps:**
1. Clone the free-lines-plugin source from FlowGram repo
2. Modify the path calculation logic
3. Implement A* or similar pathfinding
4. Publish as `@your-org/custom-lines-plugin`
5. Replace in package.json

**Pros:**
- Full control over line rendering
- Can implement any routing algorithm
- Can add waypoint support
- Maintainable as separate package

**Cons:**
- Need to maintain fork
- May need updates when FlowGram updates

### Option B: Service Override (If Possible)
**Feasibility:** UNKNOWN (need to investigate)  
**Effort:** Medium (2-4 days)  
**Control:** Depends on service API

**Steps:**
1. Find WorkflowLinesManager or similar service
2. Create custom implementation
3. Override in dependency injection
4. Implement custom path calculation

**Pros:**
- No fork needed
- Uses official plugin system

**Cons:**
- May not have access to rendering
- API might be limited
- Less control

### Option C: Canvas Layer Override
**Feasibility:** LOW  
**Effort:** High (5-7 days)  
**Control:** Medium

**Steps:**
1. Create custom canvas layer
2. Intercept line rendering
3. Draw custom paths on top
4. Handle interactions

**Pros:**
- No fork needed

**Cons:**
- Complex implementation
- Performance concerns
- May conflict with built-in rendering

## Recommended: Fork Approach

Given that:
1. Plugin hooks don't exist for line customization
2. Default routing is fundamentally flawed (crosses nodes)
3. We need full control over path calculation

**We should fork `@flowgram.ai/free-lines-plugin`**

## Implementation Plan

### Phase 2A: Fork and Setup (1 day)
1. **Find source code**
   - Check FlowGram GitHub for packages/free-lines-plugin
   - Clone or copy source

2. **Create local package**
   ```
   gui_v2/src/modules/skill-editor/custom-lines-plugin-fork/
   ├── src/
   │   ├── line-renderer.ts
   │   ├── path-calculator.ts
   │   ├── routing-algorithm.ts
   │   └── index.ts
   ├── package.json
   └── tsconfig.json
   ```

3. **Setup build**
   - Configure TypeScript
   - Test basic rendering

### Phase 2B: Implement Routing Algorithm (2-3 days)

#### Algorithm: Orthogonal A* Pathfinding

**Goal:** Find path from source to target that avoids all nodes

**Pseudocode:**
```typescript
function calculatePath(from: Point, to: Point, obstacles: Rectangle[]): Point[] {
  // 1. Create grid around nodes
  const grid = createNavigationGrid(obstacles, gridSize = 20);
  
  // 2. Run A* pathfinding
  const path = aStar(from, to, grid, {
    heuristic: manhattanDistance,
    allowDiagonal: false, // Force orthogonal
  });
  
  // 3. Simplify path (remove redundant points)
  const simplified = simplifyOrthogonalPath(path);
  
  // 4. Add padding around nodes
  const padded = addNodePadding(simplified, obstacles, padding = 10);
  
  // 5. Convert to SVG path
  return pathToSVG(padded);
}
```

**Key Features:**
- Grid-based navigation
- Manhattan distance heuristic
- Obstacle avoidance
- Path simplification
- Configurable padding

### Phase 2C: Integration (1 day)

1. **Replace plugin**
   ```typescript
   // use-editor-props.tsx
   import { createCustomLinesPlugin } from '../custom-lines-plugin-fork';
   
   plugins: () => [
     createCustomLinesPlugin({
       routingAlgorithm: 'orthogonal-astar',
       nodePadding: 10,
       gridSize: 20,
     }),
     // Remove: createFreeLinesPlugin
   ]
   ```

2. **Test scenarios**
   - Simple connections
   - Complex layouts
   - Node movement
   - Performance with many lines

### Phase 2D: Polish (1 day)

1. **Visual improvements**
   - Smooth corners (optional)
   - Better arrow positioning
   - Hover effects

2. **Performance optimization**
   - Cache grid calculations
   - Debounce path recalculation
   - Optimize A* implementation

## Routing Algorithm Details

### A* Implementation

```typescript
interface GridCell {
  x: number;
  y: number;
  walkable: boolean;
  g: number; // Cost from start
  h: number; // Heuristic to goal
  f: number; // Total cost (g + h)
  parent?: GridCell;
}

function aStar(start: Point, goal: Point, grid: GridCell[][]): Point[] {
  const openSet = new PriorityQueue<GridCell>();
  const closedSet = new Set<GridCell>();
  
  openSet.push(getCell(start), 0);
  
  while (!openSet.isEmpty()) {
    const current = openSet.pop();
    
    if (isGoal(current, goal)) {
      return reconstructPath(current);
    }
    
    closedSet.add(current);
    
    for (const neighbor of getNeighbors(current, grid)) {
      if (closedSet.has(neighbor) || !neighbor.walkable) continue;
      
      const tentativeG = current.g + distance(current, neighbor);
      
      if (tentativeG < neighbor.g) {
        neighbor.parent = current;
        neighbor.g = tentativeG;
        neighbor.h = manhattanDistance(neighbor, goal);
        neighbor.f = neighbor.g + neighbor.h;
        
        if (!openSet.contains(neighbor)) {
          openSet.push(neighbor, neighbor.f);
        }
      }
    }
  }
  
  return []; // No path found - fallback to direct line
}
```

### Grid Creation

```typescript
function createNavigationGrid(
  nodes: Rectangle[],
  gridSize: number,
  bounds: Rectangle
): GridCell[][] {
  const grid: GridCell[][] = [];
  
  for (let y = bounds.top; y < bounds.bottom; y += gridSize) {
    const row: GridCell[] = [];
    for (let x = bounds.left; x < bounds.right; x += gridSize) {
      const point = { x, y };
      const walkable = !isInsideAnyNode(point, nodes);
      
      row.push({
        x, y, walkable,
        g: Infinity,
        h: 0,
        f: Infinity,
      });
    }
    grid.push(row);
  }
  
  return grid;
}
```

## Timeline

- **Phase 2A:** 1 day - Fork and setup
- **Phase 2B:** 2-3 days - Implement routing
- **Phase 2C:** 1 day - Integration
- **Phase 2D:** 1 day - Polish

**Total:** 5-6 days

## Success Criteria

- [ ] Lines never cross nodes
- [ ] Orthogonal routing (H-V-H segments)
- [ ] Smooth path around obstacles
- [ ] Good performance (<100ms per path)
- [ ] Works with node movement
- [ ] Handles complex layouts

## Next Steps

1. **Investigate FlowGram source**
   - Find free-lines-plugin source code
   - Understand current implementation
   - Identify what to modify

2. **Prototype routing algorithm**
   - Implement A* in isolation
   - Test with sample data
   - Verify it avoids nodes

3. **Create fork**
   - Copy plugin source
   - Integrate routing algorithm
   - Test in skill editor

Would you like me to proceed with finding and forking the free-lines-plugin?
