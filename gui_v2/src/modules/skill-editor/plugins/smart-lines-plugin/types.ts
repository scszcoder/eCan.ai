/**
 * Smart Lines Plugin - Type Definitions
 * Implements node-avoiding orthogonal routing
 */

export interface Point {
  x: number;
  y: number;
}

export interface Rectangle {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface GridCell {
  x: number;
  y: number;
  walkable: boolean;
  g: number; // Cost from start
  h: number; // Heuristic to goal
  f: number; // Total cost (g + h)
  parent?: GridCell;
}

export interface PathSegment {
  start: Point;
  end: Point;
  direction: 'horizontal' | 'vertical';
}

export interface RoutingOptions {
  gridSize: number;
  nodePadding: number;
  preferredDirection?: 'horizontal' | 'vertical';
  cornerRadius?: number;
}

export interface SmartLinesPluginOptions {
  gridSize?: number;
  nodePadding?: number;
  debug?: boolean;
  enableLogging?: boolean;
}
