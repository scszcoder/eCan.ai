/**
 * Type definitions for custom lines plugin
 * These are exploratory - we'll refine them based on what we discover
 */

// Basic line structure (to be refined)
export interface WorkflowLine {
  id: string;
  from: {
    nodeId: string;
    portId: string;
    position?: { x: number; y: number };
  };
  to: {
    nodeId: string;
    portId: string;
    position?: { x: number; y: number };
  };
  data?: Record<string, any>;
  path?: string; // SVG path string
  waypoints?: Point[];
}

export interface Point {
  x: number;
  y: number;
}

export interface Waypoint extends Point {
  id?: string;
  type?: 'auto' | 'manual'; // auto-generated vs user-placed
}

// Routing algorithm types
export type RoutingAlgorithm = 'direct' | 'orthogonal' | 'curved' | 'custom';

export interface RoutingOptions {
  algorithm: RoutingAlgorithm;
  gridSize?: number;
  avoidNodes?: boolean;
  cornerRadius?: number;
  minSegmentLength?: number;
}

// Path calculation result
export interface CalculatedPath {
  waypoints: Waypoint[];
  svgPath: string;
  segments: LineSegment[];
}

export interface LineSegment {
  start: Point;
  end: Point;
  direction: 'horizontal' | 'vertical' | 'diagonal';
  length: number;
}

// Orthogonal routing specific
export interface OrthogonalRoute {
  points: Point[];
  turns: Point[]; // Points where direction changes
  totalLength: number;
  segments: {
    horizontal: LineSegment[];
    vertical: LineSegment[];
  };
}

// Plugin context (to be discovered)
export interface PluginContext {
  document?: any;
  linesManager?: any;
  playground?: any;
  commandService?: any;
  get?: (serviceName: string) => any;
}
