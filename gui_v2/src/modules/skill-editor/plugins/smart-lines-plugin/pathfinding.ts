/**
 * A* Pathfinding Algorithm for Node-Avoiding Routing
 */

import { Point, Rectangle, GridCell, PathSegment } from './types';

/**
 * Priority Queue implementation for A* algorithm
 */
class PriorityQueue<T> {
  private items: Array<{ item: T; priority: number }> = [];

  push(item: T, priority: number): void {
    this.items.push({ item, priority });
    this.items.sort((a, b) => a.priority - b.priority);
  }

  pop(): T | undefined {
    return this.items.shift()?.item;
  }

  isEmpty(): boolean {
    return this.items.length === 0;
  }

  contains(item: T): boolean {
    return this.items.some(i => i.item === item);
  }
}

/**
 * Calculate Manhattan distance between two points
 */
function manhattanDistance(a: Point, b: Point): number {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

/**
 * Check if a point is inside a rectangle (with padding)
 */
function isPointInRectangle(point: Point, rect: Rectangle, padding: number = 0): boolean {
  return (
    point.x >= rect.x - padding &&
    point.x <= rect.x + rect.width + padding &&
    point.y >= rect.y - padding &&
    point.y <= rect.y + rect.height + padding
  );
}

/**
 * Check if a point is inside any of the obstacle rectangles
 */
function isPointInObstacles(point: Point, obstacles: Rectangle[], padding: number): boolean {
  return obstacles.some(rect => isPointInRectangle(point, rect, padding));
}

/**
 * Create a navigation grid around obstacles
 */
export function createNavigationGrid(
  start: Point,
  end: Point,
  obstacles: Rectangle[],
  gridSize: number,
  padding: number
): GridCell[][] {
  // Calculate bounds
  const allPoints = [start, end, ...obstacles.flatMap(r => [
    { x: r.x, y: r.y },
    { x: r.x + r.width, y: r.y + r.height }
  ])];
  
  const minX = Math.min(...allPoints.map(p => p.x)) - padding * 2;
  const maxX = Math.max(...allPoints.map(p => p.x)) + padding * 2;
  const minY = Math.min(...allPoints.map(p => p.y)) - padding * 2;
  const maxY = Math.max(...allPoints.map(p => p.y)) + padding * 2;

  const grid: GridCell[][] = [];
  const rows = Math.ceil((maxY - minY) / gridSize);
  const cols = Math.ceil((maxX - minX) / gridSize);

  for (let row = 0; row < rows; row++) {
    const gridRow: GridCell[] = [];
    for (let col = 0; col < cols; col++) {
      const x = minX + col * gridSize;
      const y = minY + row * gridSize;
      const point = { x, y };
      const walkable = !isPointInObstacles(point, obstacles, padding);

      gridRow.push({
        x,
        y,
        walkable,
        g: Infinity,
        h: 0,
        f: Infinity,
      });
    }
    grid.push(gridRow);
  }

  return grid;
}

/**
 * Get the grid cell closest to a point
 */
function getClosestCell(point: Point, grid: GridCell[][]): GridCell | null {
  if (grid.length === 0 || grid[0].length === 0) return null;

  let closest: GridCell | null = null;
  let minDist = Infinity;

  for (const row of grid) {
    for (const cell of row) {
      const dist = manhattanDistance(point, cell);
      if (dist < minDist) {
        minDist = dist;
        closest = cell;
      }
    }
  }

  return closest;
}

/**
 * Find the nearest walkable cell to a given cell
 */
function findNearestWalkableCell(cell: GridCell, grid: GridCell[][]): GridCell | null {
  if (cell.walkable) return cell;
  
  let nearest: GridCell | null = null;
  let minDist = Infinity;
  
  for (const row of grid) {
    for (const gridCell of row) {
      if (gridCell.walkable) {
        const dist = manhattanDistance(cell, gridCell);
        if (dist < minDist) {
          minDist = dist;
          nearest = gridCell;
        }
      }
    }
  }
  
  return nearest;
}

/**
 * Get neighbors of a cell (only orthogonal - no diagonals)
 */
function getNeighbors(cell: GridCell, grid: GridCell[][]): GridCell[] {
  const neighbors: GridCell[] = [];
  const directions = [
    { dx: 0, dy: -1 }, // Up
    { dx: 1, dy: 0 },  // Right
    { dx: 0, dy: 1 },  // Down
    { dx: -1, dy: 0 }, // Left
  ];

  for (const dir of directions) {
    const newX = cell.x + dir.dx * (grid[0]?.[1]?.x - grid[0]?.[0]?.x || 20);
    const newY = cell.y + dir.dy * (grid[1]?.[0]?.y - grid[0]?.[0]?.y || 20);

    const neighbor = grid
      .flatMap(row => row)
      .find(c => Math.abs(c.x - newX) < 1 && Math.abs(c.y - newY) < 1);

    if (neighbor && neighbor.walkable) {
      neighbors.push(neighbor);
    }
  }

  return neighbors;
}

/**
 * Reconstruct path from goal to start
 */
function reconstructPath(goal: GridCell): Point[] {
  const path: Point[] = [];
  let current: GridCell | undefined = goal;

  while (current) {
    path.unshift({ x: current.x, y: current.y });
    current = current.parent;
  }

  return path;
}

/**
 * A* pathfinding algorithm
 */
export function findPath(
  start: Point,
  goal: Point,
  obstacles: Rectangle[],
  gridSize: number = 20,
  padding: number = 10
): Point[] {
  // Create navigation grid
  const grid = createNavigationGrid(start, goal, obstacles, gridSize, padding);

  if (grid.length === 0 || grid[0].length === 0) {
    console.warn('[SmartLinesPlugin] Grid is empty');
    // Fallback to direct line
    return [start, goal];
  }

  // Find start and goal cells
  const startCell = getClosestCell(start, grid);
  const goalCell = getClosestCell(goal, grid);

  if (!startCell || !goalCell) {
    console.warn('[SmartLinesPlugin] Could not find start or goal cell', { 
      hasStart: !!startCell, 
      hasGoal: !!goalCell,
      gridSize: `${grid.length}x${grid[0]?.length}`,
    });
    return [start, goal];
  }
  
  // If start or goal is not walkable, find nearest walkable cell
  let actualStart = startCell;
  let actualGoal = goalCell;
  
  if (!startCell.walkable) {
    actualStart = findNearestWalkableCell(startCell, grid) || startCell;
  }
  
  if (!goalCell.walkable) {
    actualGoal = findNearestWalkableCell(goalCell, grid) || goalCell;
  }

  // Initialize start cell
  actualStart.g = 0;
  actualStart.h = manhattanDistance(actualStart, actualGoal);
  actualStart.f = actualStart.h;

  const openSet = new PriorityQueue<GridCell>();
  const closedSet = new Set<GridCell>();

  openSet.push(actualStart, actualStart.f);

  while (!openSet.isEmpty()) {
    const current = openSet.pop();
    if (!current) break;

    // Check if we reached the goal
    if (manhattanDistance(current, actualGoal) < gridSize) {
      const path = reconstructPath(current);
      // Add actual start and end points
      return [start, ...path, goal];
    }

    closedSet.add(current);

    // Check neighbors
    for (const neighbor of getNeighbors(current, grid)) {
      if (closedSet.has(neighbor)) continue;

      const tentativeG = current.g + manhattanDistance(current, neighbor);

      if (tentativeG < neighbor.g) {
        neighbor.parent = current;
        neighbor.g = tentativeG;
        neighbor.h = manhattanDistance(neighbor, actualGoal);
        neighbor.f = neighbor.g + neighbor.h;

        if (!openSet.contains(neighbor)) {
          openSet.push(neighbor, neighbor.f);
        }
      }
    }
  }

  // No path found - return direct line
  console.warn('[SmartLinesPlugin] No path found, using direct line');
  return [start, goal];
}

/**
 * Simplify path by removing redundant points
 */
export function simplifyPath(path: Point[]): Point[] {
  if (path.length <= 2) return path;

  const simplified: Point[] = [path[0]];

  for (let i = 1; i < path.length - 1; i++) {
    const prev = path[i - 1];
    const current = path[i];
    const next = path[i + 1];

    // Check if current point is on the same line as prev and next
    const dx1 = current.x - prev.x;
    const dy1 = current.y - prev.y;
    const dx2 = next.x - current.x;
    const dy2 = next.y - current.y;

    // If not collinear, keep the point
    if (dx1 * dy2 !== dy1 * dx2) {
      simplified.push(current);
    }
  }

  simplified.push(path[path.length - 1]);
  return simplified;
}

/**
 * Convert path to SVG path string
 */
export function pathToSVG(path: Point[], cornerRadius: number = 0): string {
  if (path.length < 2) return '';

  let svgPath = `M ${path[0].x} ${path[0].y}`;

  if (cornerRadius === 0) {
    // Simple straight lines
    for (let i = 1; i < path.length; i++) {
      svgPath += ` L ${path[i].x} ${path[i].y}`;
    }
  } else {
    // Rounded corners
    for (let i = 1; i < path.length; i++) {
      const current = path[i];
      const prev = path[i - 1];

      if (i === path.length - 1) {
        // Last point - straight line
        svgPath += ` L ${current.x} ${current.y}`;
      } else {
        const next = path[i + 1];
        const dx1 = current.x - prev.x;
        const dy1 = current.y - prev.y;
        const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1);

        const dx2 = next.x - current.x;
        const dy2 = next.y - current.y;
        const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);

        const radius = Math.min(cornerRadius, len1 / 2, len2 / 2);

        // Point before corner
        const beforeX = current.x - (dx1 / len1) * radius;
        const beforeY = current.y - (dy1 / len1) * radius;

        // Point after corner
        const afterX = current.x + (dx2 / len2) * radius;
        const afterY = current.y + (dy2 / len2) * radius;

        svgPath += ` L ${beforeX} ${beforeY}`;
        svgPath += ` Q ${current.x} ${current.y} ${afterX} ${afterY}`;
      }
    }
  }

  return svgPath;
}
