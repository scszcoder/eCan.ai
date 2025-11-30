/**
 * Smart Lines Plugin for FlowGram.ai
 * Implements node-avoiding orthogonal routing using A* pathfinding
 */

import {
  definePluginCreator,
  PluginCreator,
  FreeLayoutPluginContext,
} from '@flowgram.ai/free-layout-editor';
import { WorkflowLineRenderContributionFactory, WorkflowLinesManager } from '@flowgram.ai/free-layout-core';
import { SmartLinesPluginOptions, Rectangle, Point } from './types';
import { findPath, simplifyPath, pathToSVG } from './pathfinding';
import { SmartLineContribution, SMART_LINE_TYPE, createSmartLineContribution } from './line-contribution';

/**
 * Creates a smart lines plugin with node-avoiding routing
 */
export const createSmartLinesPlugin: PluginCreator<SmartLinesPluginOptions> = definePluginCreator<
  SmartLinesPluginOptions,
  FreeLayoutPluginContext
>({
  onInit(ctx, options = {}) {
    console.log('[SmartLinesPlugin] 🚀 onInit called');
  },
  
  onReady(ctx, options = {}) {
    console.log('[SmartLinesPlugin] 🚀 onReady called with options:', options);
    
    const {
      gridSize = 20,
      nodePadding = 15,
      debug = false,
      enableLogging = true,
    } = options;

    const log = (...args: any[]) => {
      if (enableLogging) {
        console.log('[SmartLinesPlugin]', ...args);
      }
    };

    log('✅ Smart Lines Plugin ready', { gridSize, nodePadding });

    // CRITICAL: Register our contribution FIRST, before createFreeLinesPlugin's onReady
    // Do this SYNCHRONOUSLY to ensure it happens before the default registration
    try {
      log('🔍 Attempting to get WorkflowLinesManager from container...');
      
      const linesManager = ctx.container.get(WorkflowLinesManager);
      
      if (linesManager) {
        log('✅ Found linesManager:', linesManager.constructor?.name);
        log('🔍 Has registerContribution?', typeof linesManager.registerContribution);
        
        if (typeof linesManager.registerContribution === 'function') {
          log('🔍 contributionFactories BEFORE registration:', linesManager.contributionFactories.length);
          log('🔍 contributionFactories types:', linesManager.contributionFactories.map((f: any) => f.type));
          log('🔍 contributionFactories details:', linesManager.contributionFactories.map((f: any) => ({ name: f.name, type: f.type, constructor: f.constructor?.name })));
          
          linesManager.registerContribution(SmartLineContributionFactory);
          log('✅ Registered smart line contribution');
          
          log('🔍 contributionFactories AFTER registration:', linesManager.contributionFactories.length);
          log('🔍 contributionFactories types:', linesManager.contributionFactories.map((f: any) => f.type));
          log('🔍 contributionFactories details:', linesManager.contributionFactories.map((f: any) => ({ name: f.name, type: f.type, constructor: f.constructor?.name })));
          
          // Force all lines to re-sync their contributions
          // This will make them pick up our newly registered contribution
          log('⏰ Setting up setTimeout to force line update...');
          setTimeout(() => {
            log('⏰ setTimeout fired! Manually forcing line updates...');
            const lines = linesManager.getAllLines?.() || [];
            log('🔍 Found', lines.length, 'lines to update');
            
            // Manually force each line to re-create its contributions
            lines.forEach((line: any, index: number) => {
              try {
                // Access the renderData
                const renderData = line._datas?.get?.('WorkflowLineRenderData');
                if (renderData) {
                  // Clear existing contributions to force re-sync
                  if (renderData.data && renderData.data.contributions) {
                    const oldSize = renderData.data.contributions.size;
                    renderData.data.contributions.clear();
                    log(`🔄 Line ${index} (${line.id}): Cleared ${oldSize} contributions`);
                    
                    // Force re-sync by calling update
                    renderData.update();
                    log(`✅ Line ${index} (${line.id}): Re-synced, now has ${renderData.data.contributions.size} contributions`);
                    
                    // Check which contribution is being used for BEZIER
                    const bezierContrib = renderData.data.contributions.get(0); // type 0 = BEZIER
                    if (bezierContrib) {
                      log(`🔍 Line ${index} BEZIER contribution:`, bezierContrib.constructor.name);
                    }
                  }
                }
              } catch (e) {
                log(`⚠️ Error updating line ${index}:`, e);
              }
            });
            
            log('✅ Finished manually updating all lines');
          }, 2000); // Increased delay to ensure lines are loaded
        } else {
          log('⚠️ linesManager has no registerContribution method');
        }
      } else {
        log('⚠️ Could not get linesManager from container');
      }
    } catch (e) {
      log('⚠️ Error registering contribution early:', e);
    }

    try {
      const document = ctx.document;
      
      if (!document) {
        log('⚠️ Document not found - cannot override line routing');
        return;
      }

      log('✅ Found document service:', document.constructor?.name);
      
      // Get lines from linesManager
      const linesManager = (document as any).linesManager;
      
      if (linesManager) {
        log('✅ Found linesManager, hooking into line rendering');
        
        // Periodically patch existing lines
        const patchLines = () => {
          // Try different methods to get lines
          let lines = null;
          
          if (typeof linesManager.getAllLines === 'function') {
            lines = linesManager.getAllLines();
          } else if (typeof linesManager.getAll === 'function') {
            lines = linesManager.getAll();
          } else if (Array.isArray(linesManager.lines)) {
            lines = linesManager.lines;
          } else if (linesManager._lines) {
            lines = Object.values(linesManager._lines);
          }
          
          if (lines && Array.isArray(lines)) {
            lines.forEach((line: any) => {
              if (!line.__smartPathPatched) {
                line.__smartPathPatched = true;
                
                // Store original path getter
                const originalPathDescriptor = Object.getOwnPropertyDescriptor(
                  Object.getPrototypeOf(line),
                  'path'
                );
                
                // Override path getter
                Object.defineProperty(line, 'path', {
                  get() {
                    // Get our smart contribution
                    const contribution = line.__smartContribution;
                    if (contribution && contribution.cachedPath) {
                      console.log('[SmartLinesPlugin] Using smart path for line:', line.id, contribution.cachedPath.substring(0, 50));
                      return contribution.cachedPath;
                    }
                    // Fallback to original
                    const fallback = originalPathDescriptor?.get?.call(this) || '';
                    console.log('[SmartLinesPlugin] Using fallback path for line:', line.id, fallback.substring(0, 50));
                    return fallback;
                  },
                  configurable: true,
                });
                
                log('✅ Patched line:', line.id);
                
                // Debug: log what properties are being accessed
                if (line.id === '823390_-749170_') {
                  const handler = {
                    get(target: any, prop: string) {
                      const value = target[prop];
                      if (prop === 'path' || prop === 'svgPath' || prop === 'd' || prop === 'pathData') {
                        console.log(`[SmartLinesPlugin] 🔍 Line ${target.id}: accessing property "${prop}":`, typeof value === 'string' ? value.substring(0, 50) : value);
                      }
                      return value;
                    }
                  };
                  
                  // This won't work for existing objects, but log for debugging
                  console.log('[SmartLinesPlugin] 🔍 Monitoring line property access for:', line.id);
                }
              }
            });
          } else {
            log('⚠️ Could not get lines array from linesManager');
          }
        };
        
        // Patch lines periodically
        setInterval(patchLines, 1000);
        patchLines();
        
        // Explore rendering layer
        const exploreRendering = () => {
          const lines = linesManager.getAllLines?.() || linesManager.getAll?.() || 
                       linesManager.lines || (linesManager._lines ? Object.values(linesManager._lines) : null);
          
          if (lines && lines.length > 0) {
            const testLine = lines.find((l: any) => l.id === '823390_-749170_') || lines[0];
            
            log('🔍 Exploring line rendering for:', testLine.id);
            log('🔍 Line keys:', Object.keys(testLine));
            log('🔍 Line prototype:', Object.getPrototypeOf(testLine).constructor.name);
            log('🔍 Line prototype keys:', Object.getOwnPropertyNames(Object.getPrototypeOf(testLine)));
            
            // Check for rendering-related properties
            const renderProps = ['render', 'renderer', 'view', 'element', 'svgElement', 'pathElement', 
                                'renderData', 'renderPath', 'draw', 'paint', 'graphics'];
            
            renderProps.forEach(prop => {
              if (testLine[prop]) {
                log(`🔍 Found ${prop}:`, typeof testLine[prop], testLine[prop].constructor?.name);
              }
            });
            
            // Check the contribution
            const contribution = testLine.__smartContribution;
            if (contribution) {
              log('🔍 Contribution cachedPath:', contribution.cachedPath?.substring(0, 80));
            }
            
            // Check if there's a path getter
            const pathDescriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(testLine), 'path');
            log('🔍 Has path property descriptor?', !!pathDescriptor);
            if (pathDescriptor) {
              log('🔍 Path descriptor:', {
                hasGetter: !!pathDescriptor.get,
                hasSetter: !!pathDescriptor.set,
                configurable: pathDescriptor.configurable,
                enumerable: pathDescriptor.enumerable,
              });
              
              // Try to get the current path value
              try {
                const currentPath = testLine.path;
                log('🔍 Current path value:', typeof currentPath, currentPath?.substring?.(0, 80));
              } catch (e) {
                log('🔍 Error getting path:', e);
              }
            }
          }
        };
        
        setTimeout(exploreRendering, 2000);
        
        // Try to override the path getter on line entities
        setTimeout(() => {
          const lines = linesManager.getAllLines?.() || linesManager.getAll?.() || 
                       linesManager.lines || (linesManager._lines ? Object.values(linesManager._lines) : null);
          
          if (lines && lines.length > 0) {
            lines.forEach((line: any) => {
              const contribution = line.__smartContribution;
              if (contribution && contribution.cachedPath && !line.__pathGetterOverridden) {
                line.__pathGetterOverridden = true;
                
                // Override the path property on the instance
                Object.defineProperty(line, 'path', {
                  get() {
                    return contribution.cachedPath;
                  },
                  configurable: true,
                });
                
                // Trigger re-render
                if (typeof line.fireRender === 'function') {
                  line.fireRender();
                  log('✅ Overrode path getter and triggered render for:', line.id);
                }
              }
            });
          }
        }, 3000);
      }

      // Try to register custom line contribution
      try {
        // Check if there's a way to register line contributions
        const playground = ctx.playground;
        
        if (playground) {
          log('✅ Found playground:', playground.constructor?.name);
          
          // Try to access line contribution registry
          const config = (playground as any).config;
          if (config) {
            log('✅ Found playground config');
            
            // Try to register our contribution
            const lineContributions = (config as any).lineContributions || [];
            log('📋 Existing line contributions:', lineContributions.length);
          }
        }
      } catch (e) {
        log('⚠️ Error accessing playground config:', e);
      }

      // Expose helper functions
      (window as any).__SMART_LINES__ = {
        calculatePath: (from: Point, to: Point, nodes: Rectangle[]) => {
          const path = findPath(from, to, nodes, gridSize, nodePadding);
          const simplified = simplifyPath(path);
          const svg = pathToSVG(simplified, 5);
          
          log('📐 Calculated path:', {
            from,
            to,
            obstacles: nodes.length,
            pathPoints: path.length,
            simplifiedPoints: simplified.length,
          });
          
          return { path, simplified, svg };
        },
        getNodeBounds: () => {
          try {
            const nodes = (document as any).nodes || [];
            return nodes.map((node: any) => ({
              x: node.x || node.position?.x || 0,
              y: node.y || node.position?.y || 0,
              width: node.width || 200,
              height: node.height || 100,
            }));
          } catch (e) {
            log('⚠️ Error getting node bounds:', e);
            return [];
          }
        },
        // Expose contribution class for testing
        SmartLineContribution,
        SMART_LINE_TYPE,
        debug,
        ctx,
      };

      log('💡 Smart routing functions exposed: window.__SMART_LINES__');

      // Log available methods for investigation
      if (debug) {
        const docMethods = Object.getOwnPropertyNames(Object.getPrototypeOf(document))
          .filter(m => typeof (document as any)[m] === 'function')
          .slice(0, 15);
        log('📋 Document methods:', docMethods);
        
        const playground = ctx.playground;
        if (playground) {
          const playgroundMethods = Object.getOwnPropertyNames(Object.getPrototypeOf(playground))
            .filter(m => typeof (playground as any)[m] === 'function')
            .slice(0, 15);
          log('📋 Playground methods:', playgroundMethods);
        }
      }

    } catch (e) {
      log('⚠️ Error setting up smart routing:', e);
    }

    log('🔍 Plugin ready. Check window.__SMART_LINES__ for routing functions.');
  },

  onDispose(ctx) {
    console.log('[SmartLinesPlugin] 🧹 Plugin disposed');
    try {
      delete (window as any).__SMART_LINES__;
    } catch {}
  },
});

/**
 * Factory class for creating smart line contributions
 * FlowGram expects a class with a static type property
 */
export class SmartLineContributionFactory {
  static type = SMART_LINE_TYPE;
  
  constructor(entity: any) {
    return new SmartLineContribution(entity) as any;
  }
}

// Also export as a factory object for compatibility
export const smartLineContributionFactory = SmartLineContributionFactory;

export * from './types';
export * from './pathfinding';
export * from './line-contribution';
