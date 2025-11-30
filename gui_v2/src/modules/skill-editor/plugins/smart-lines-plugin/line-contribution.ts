/**
 * Smart Line Render Contribution
 * Implements custom path calculation using A* pathfinding
 */

import {
  WorkflowLineRenderContribution,
  WorkflowLineEntity,
  LineType,
  LineCenterPoint,
  LinePoint,
} from '@flowgram.ai/free-layout-core';
import { IPoint, Rectangle } from '@flowgram.ai/utils';
import { findPath, simplifyPath, pathToSVG } from './pathfinding';
import { Point } from './types';

/**
 * Use BEZIER type to override the default bezier line rendering
 * FlowGram uses numeric enum values: BEZIER=0, LINE_CHART=1, STRAIGHT=2
 */
export const SMART_LINE_TYPE: LineType = 0 as LineType; // LineType.BEZIER

/**
 * Smart Line Render Contribution
 * Calculates paths that avoid nodes using A* pathfinding
 * Applies to all line types by using 'default' type
 */
export class SmartLineContribution implements WorkflowLineRenderContribution {
  static type: LineType = SMART_LINE_TYPE;

  entity: WorkflowLineEntity;
  private cachedPath?: string;
  private cachedBounds?: Rectangle;
  private cachedCenter?: LineCenterPoint;
  private lastFromPos?: IPoint;
  private lastToPos?: IPoint;

  constructor(entity: WorkflowLineEntity) {
    this.entity = entity;
    
    // Store reference to this contribution on the entity so our monkey-patch can access it
    (entity as any).__smartContribution = this;
    
    const lineType = (entity as any).type || (entity as any).lineType || 'unknown';
    console.log('🚨🚨🚨 [SmartLineContribution] CONSTRUCTOR CALLED for entity:', entity?.id || 'unknown', 'type:', lineType);
    console.log('🚨🚨🚨 [SmartLineContribution] This contribution class:', this.constructor.name);
    
    // Check what's in the contributions map
    setTimeout(() => {
      const renderData = (entity as any)._datas?.get?.('WorkflowLineRenderData');
      if (renderData && renderData.data && renderData.data.contributions) {
        const bezierContrib = renderData.data.contributions.get('bezier');
        console.log('🔍🔍🔍 [SmartLineContribution] BEZIER contribution class for', entity.id, ':', bezierContrib?.constructor?.name);
        console.log('🔍🔍🔍 [SmartLineContribution] Is it ours?', bezierContrib === this);
      }
    }, 100);
    
    // Try to get initial positions from entity
    try {
      const from = (entity as any).from || (entity as any).fromPort;
      const to = (entity as any).to || (entity as any).toPort;
      
      if (from && to) {
        console.log('[SmartLineContribution] Found initial positions:', { from, to });
        // Calculate initial path
        this.calculatePath(from, to);
      } else {
        // Initialize with a simple path so line is visible
        this.cachedPath = 'M 0 0 L 100 100';
      }
    } catch (e) {
      console.warn('[SmartLineContribution] Error in constructor:', e);
      this.cachedPath = 'M 0 0 L 100 100';
    }
  }

  /**
   * Get the SVG path for this line
   */
  get path(): string {
    const path = this.cachedPath || this.getFallbackPath();
    console.log('🎯🎯🎯 [SmartLineContribution] PATH GETTER CALLED FOR:', this.entity.id, 'returning:', path.substring(0, 80));
    return path;
  }
  
  /**
   * Get fallback direct line path
   */
  private getFallbackPath(): string {
    const fromPos = this.lastFromPos || { x: 0, y: 0 };
    const toPos = this.lastToPos || { x: 100, y: 100 };
    return `M ${fromPos.x} ${fromPos.y} L ${toPos.x} ${toPos.y}`;
  }

  /**
   * Calculate distance from a point to this line
   */
  calcDistance(pos: IPoint): number {
    // Simple bounding box check for now
    const bounds = this.bounds;
    if (!bounds) return Infinity;

    const dx = Math.max(bounds.x - pos.x, 0, pos.x - (bounds.x + bounds.width));
    const dy = Math.max(bounds.y - pos.y, 0, pos.y - (bounds.y + bounds.height));
    return Math.sqrt(dx * dx + dy * dy);
  }

  /**
   * Get the bounding box of this line
   */
  get bounds(): Rectangle {
    if (this.cachedBounds) {
      return this.cachedBounds;
    }

    // Calculate from path points
    const fromPos = this.lastFromPos || { x: 0, y: 0 };
    const toPos = this.lastToPos || { x: 0, y: 0 };

    const minX = Math.min(fromPos.x, toPos.x);
    const minY = Math.min(fromPos.y, toPos.y);
    const maxX = Math.max(fromPos.x, toPos.x);
    const maxY = Math.max(fromPos.y, toPos.y);

    this.cachedBounds = {
      x: minX,
      y: minY,
      width: maxX - minX,
      height: maxY - minY,
    };

    return this.cachedBounds;
  }

  /**
   * Get the center point of this line
   */
  get center(): LineCenterPoint | undefined {
    if (this.cachedCenter) {
      return this.cachedCenter;
    }

    const fromPos = this.lastFromPos;
    const toPos = this.lastToPos;

    if (!fromPos || !toPos) return undefined;

    this.cachedCenter = {
      x: (fromPos.x + toPos.x) / 2,
      y: (fromPos.y + toPos.y) / 2,
    };

    return this.cachedCenter;
  }

  /**
   * Calculate path between two positions
   */
  private calculatePath(fromPos: any, toPos: any): void {
    console.log('[SmartLineContribution] calculatePath called:', { fromPos, toPos });
    
    // Extract actual coordinates from PORT entities, not node entities
    // The line entity has fromPort and toPort with the actual port positions
    let from: IPoint;
    let to: IPoint;
    
    // Try to get port positions from line entity first
    const fromPort = (this.entity as any).fromPort;
    const toPort = (this.entity as any).toPort;
    
    if (fromPort && (fromPort as any).bounds) {
      const bounds = (fromPort as any).bounds;
      from = {
        x: bounds.x + (bounds.width || 0) / 2,
        y: bounds.y + (bounds.height || 0) / 2,
      };
    } else {
      from = { x: 0, y: 0 }; // Fallback
    }
    
    if (toPort && (toPort as any).bounds) {
      const bounds = (toPort as any).bounds;
      to = {
        x: bounds.x + (bounds.width || 0) / 2,
        y: bounds.y + (bounds.height || 0) / 2,
      };
    } else {
      to = { x: 0, y: 0 }; // Fallback
    }
    
    // If we got valid port positions, skip the old node-based extraction
    if (fromPort && toPort && from.x !== 0 && to.x !== 0) {
      console.log('[SmartLineContribution] Using port positions:', { from, to });
      // Skip to path calculation
    } else {
      // Fallback to old method (extract from node entities)
    
    try {
      // Try to get position from entity
      if (typeof fromPos === 'object' && fromPos !== null) {
        // Check if it's already a point
        if (typeof fromPos.x === 'number' && typeof fromPos.y === 'number') {
          from = fromPos;
        } else {
          // It's an entity - need to get bounds or position
          // Try various ways to get position
          const bounds = (fromPos as any).bounds;
          const transform = (fromPos as any).transform;
          
          // Debug: log what's available
          if (!this._posDebugLogged) {
            this._posDebugLogged = true;
            
            // Deep investigation of the entity structure
            const entity = fromPos as any;
            console.group('[SmartLineContribution] Investigating fromPos entity');
            console.log('Entity type:', entity.constructor?.name);
            console.log('Is node?', !!entity.flowNodeType);
            console.log('Has bounds?', !!bounds);
            console.log('Bounds value:', bounds);
            console.log('Has transform?', !!transform);
            console.log('Transform value:', transform);
            
            // Check for port-related properties
            console.log('Has ports?', !!entity.ports);
            console.log('Ports value:', entity.ports);
            console.log('Has position?', !!entity.position);
            console.log('Position value:', entity.position);
            console.log('Has absolutePosition?', !!entity.absolutePosition);
            console.log('AbsolutePosition value:', entity.absolutePosition);
            
            // Check line entity for port info
            console.log('Line entity:', this.entity);
            console.log('Line from:', (this.entity as any).from);
            console.log('Line to:', (this.entity as any).to);
            
            const fromPort = (this.entity as any).fromPort;
            const toPort = (this.entity as any).toPort;
            console.log('Line fromPort:', fromPort);
            console.log('Line toPort:', toPort);
            
            // Investigate port entities
            if (fromPort) {
              console.log('fromPort keys:', Object.keys(fromPort));
              console.log('fromPort.bounds:', (fromPort as any).bounds);
              console.log('fromPort.transform:', (fromPort as any).transform);
              console.log('fromPort.position:', (fromPort as any).position);
              console.log('fromPort.absolutePosition:', (fromPort as any).absolutePosition);
              console.log('fromPort.center:', (fromPort as any).center);
              console.log('fromPort.x:', (fromPort as any).x);
              console.log('fromPort.y:', (fromPort as any).y);
            }
            
            // List all keys
            console.log('All entity keys:', Object.keys(entity));
            console.groupEnd();
          }
          
          if (bounds && typeof bounds.x === 'number' && typeof bounds.y === 'number') {
            // Use center of bounds
            from = {
              x: bounds.x + (bounds.width || 0) / 2,
              y: bounds.y + (bounds.height || 0) / 2,
            };
          } else if (transform && typeof transform.x === 'number' && typeof transform.y === 'number') {
            from = { x: transform.x, y: transform.y };
          } else {
            from = {
              x: fromPos.x ?? fromPos.position?.x ?? fromPos.absolutePosition?.x ?? 0,
              y: fromPos.y ?? fromPos.position?.y ?? fromPos.absolutePosition?.y ?? 0,
            };
          }
        }
      } else {
        from = { x: 0, y: 0 };
      }
      
      if (typeof toPos === 'object' && toPos !== null) {
        if (typeof toPos.x === 'number' && typeof toPos.y === 'number') {
          to = toPos;
        } else {
          const bounds = (toPos as any).bounds;
          const transform = (toPos as any).transform;
          
          if (bounds && typeof bounds.x === 'number' && typeof bounds.y === 'number') {
            to = {
              x: bounds.x + (bounds.width || 0) / 2,
              y: bounds.y + (bounds.height || 0) / 2,
            };
          } else if (transform && typeof transform.x === 'number' && typeof transform.y === 'number') {
            to = { x: transform.x, y: transform.y };
          } else {
            to = {
              x: toPos.x ?? toPos.position?.x ?? toPos.absolutePosition?.x ?? 0,
              y: toPos.y ?? toPos.position?.y ?? toPos.absolutePosition?.y ?? 0,
            };
          }
        }
      } else {
        to = { x: 0, y: 0 };
      }
      
      console.log('[SmartLineContribution] Extracted coordinates (fallback):', { from, to });
    } catch (e) {
      console.error('[SmartLineContribution] Error extracting positions:', e);
      from = { x: 0, y: 0 };
      to = { x: 100, y: 100 };
    }
    } // End of fallback extraction
    
    // Store positions
    this.lastFromPos = from;
    this.lastToPos = to;

    // Clear cache
    this.cachedPath = undefined;
    this.cachedBounds = undefined;
    this.cachedCenter = undefined;

    // Validate positions
    if (typeof from.x !== 'number' || typeof from.y !== 'number' ||
        typeof to.x !== 'number' || typeof to.y !== 'number') {
      console.warn('[SmartLineContribution] Invalid coordinates after extraction:', { from, to });
      this.cachedPath = `M 0 0 L 100 100`; // Fallback
      return;
    }

    // Get obstacles (all nodes except the connected ones)
    const obstacles = this.getObstacles();

    // Calculate path using A* pathfinding
    const start: Point = { x: from.x, y: from.y };
    const end: Point = { x: to.x, y: to.y };

    try {
      // Use large grid size (100) and NO padding (0) to allow paths close to obstacles
      // Grid size of 100 means ~3-4 cells per 360px node
      // This creates a coarser grid that's faster to search
      // Padding of 0 allows the path to go right next to obstacles
      const pathPoints = findPath(start, end, obstacles, 100, 0);
      const simplified = simplifyPath(pathPoints);
      const svgPath = pathToSVG(simplified, 5);

      this.cachedPath = svgPath;
      
      // Force the line entity to use our new path and trigger re-render
      if (this.entity) {
        (this.entity as any)._path = svgPath;
        (this.entity as any).pathData = svgPath;
        
        // Trigger re-render!
        if (typeof (this.entity as any).fireRender === 'function') {
          (this.entity as any).fireRender();
          console.log('[SmartLineContribution] 🎨 Triggered fireRender for line:', this.entity.id);
        }
      }

      // Detailed logging for first few paths
      if (!this._logCount) this._logCount = 0;
      this._logCount++;
      
      if (this._logCount <= 1) {
        const isRouted = pathPoints.length > 2;
        console.log(`[SmartLineContribution] Path calculated (${isRouted ? 'ROUTED' : 'DIRECT'}):`, {
          lineId: this.entity?.id,
          from: start,
          to: end,
          obstacles: obstacles.length,
          pathPoints: pathPoints.length,
          pathDetail: pathPoints,
          simplified: simplified.length,
          simplifiedDetail: simplified,
          svgPath: svgPath.substring(0, 150),
          isRouted,
        });
      }
    } catch (error) {
      console.error('[SmartLineContribution] Error calculating path:', error);
      // Fallback to direct line
      this.cachedPath = `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
    }
  }

  /**
   * Update the line path when nodes move
   */
  update(params: { fromPos: any; toPos: any }): void {
    console.log('🔥🔥🔥 [SmartLineContribution] UPDATE() CALLED for:', this.entity.id, 'params:', params);
    this.calculatePath(params.fromPos, params.toPos);
    
    // Force the line entity to use our new path
    if (this.entity && this.cachedPath) {
      // Try to set the path directly on the entity
      (this.entity as any)._path = this.cachedPath;
      (this.entity as any).pathData = this.cachedPath;
      
      console.log('[SmartLineContribution] Set path on entity:', this.cachedPath.substring(0, 50));
    }
  }

  private _updateCount?: number;
  private _logCount?: number;
  private _posDebugLogged?: boolean;
  private _docDebugLogged?: boolean;

  /**
   * Get all nodes as obstacles (except the connected nodes)
   */
  private getObstacles(): Rectangle[] {
    try {
      // Try to get document from entity
      const document = (this.entity as any).document || (this.entity as any)._document;
      
      if (!document) {
        console.warn('[SmartLineContribution] No document found');
        return [];
      }

      // Debug: log document structure once
      if (!this._docDebugLogged) {
        this._docDebugLogged = true;
        console.log('[SmartLineContribution] Document structure:', {
          hasNodes: !!(document as any).nodes,
          nodesLength: (document as any).nodes?.length,
          hasGetAllNodes: typeof (document as any).getAllNodes === 'function',
          hasNodeList: !!(document as any).nodeList,
          documentKeys: Object.keys(document).slice(0, 20),
        });
      }

      // Get all nodes - try different methods
      let nodes = (document as any).nodes || [];
      if (nodes.length === 0 && typeof (document as any).getAllNodes === 'function') {
        nodes = (document as any).getAllNodes() || [];
      }
      if (nodes.length === 0 && (document as any).nodeList) {
        nodes = (document as any).nodeList || [];
      }
      
      // Get connected node IDs from line entity
      const fromNodeId = (this.entity as any).from?.id || (this.entity as any).from?._id;
      const toNodeId = (this.entity as any).to?.id || (this.entity as any).to?._id;
      
      console.log('[SmartLineContribution] Excluding nodes:', { fromNodeId, toNodeId });

      // Convert nodes to rectangles, excluding connected nodes
      const obstacles: Rectangle[] = [];
      
      for (const node of nodes) {
        // Skip connected nodes
        if (node.id === fromNodeId || node.id === toNodeId) {
          continue;
        }

        // Get node bounds - use bounds property like we do for line positions
        const bounds = (node as any).bounds;
        let x = 0, y = 0, width = 200, height = 100;
        
        if (bounds && typeof bounds.x === 'number' && typeof bounds.y === 'number') {
          x = bounds.x;
          y = bounds.y;
          width = bounds.width || 200;
          height = bounds.height || 100;
        } else {
          // Fallback to direct properties
          x = node.x ?? node.position?.x ?? 0;
          y = node.y ?? node.position?.y ?? 0;
          width = node.width ?? 200;
          height = node.height ?? 100;
        }

        obstacles.push({ x, y, width, height });
      }

      return obstacles;
    } catch (error) {
      console.error('[SmartLineContribution] Error getting obstacles:', error);
      return [];
    }
  }
}

/**
 * Factory function to create smart line contributions
 */
export function createSmartLineContribution(entity: WorkflowLineEntity): WorkflowLineRenderContribution {
  return new SmartLineContribution(entity);
}
