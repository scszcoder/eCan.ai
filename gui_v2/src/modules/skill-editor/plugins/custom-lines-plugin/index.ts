/**
 * Custom Lines Plugin for FlowGram.ai
 * 
 * Phase 1: Minimal plugin to investigate the plugin API
 * Goals:
 * - Intercept line rendering events
 * - Log available hooks and methods
 * - Test if we can override default line behavior
 */

import {
  definePluginCreator,
  PluginCreator,
  FreeLayoutPluginContext,
} from '@flowgram.ai/free-layout-editor';
import { inspectContext, inspectLine, getMethods } from './debug-utils';

export interface CustomLinesPluginOptions {
  debug?: boolean;
  enableLogging?: boolean;
  detailedInspection?: boolean;
}

/**
 * Creates a custom lines plugin for investigating the FlowGram API
 */
export const createCustomLinesPlugin: PluginCreator<CustomLinesPluginOptions> = definePluginCreator<
  CustomLinesPluginOptions,
  FreeLayoutPluginContext
>({
  onInit(ctx, options = {}) {
    const { debug = true, enableLogging = true, detailedInspection = false } = options;

    const log = (...args: any[]) => {
      if (enableLogging) {
        console.log('[CustomLinesPlugin]', ...args);
      }
    };

    log('✅ Plugin initialized with options:', options);
    
    if (detailedInspection) {
      inspectContext(ctx);
    } else {
      log('Context type:', ctx.constructor?.name);
      log('Available properties:', Object.keys(ctx).filter(k => typeof (ctx as any)[k] === 'object'));
    }
    
    // Try to access the lines manager
    try {
      const linesManager = (ctx as any).linesManager;
      if (linesManager) {
        log('✅ Found linesManager:', linesManager.constructor?.name);
        if (detailedInspection) {
          log('LinesManager methods:', getMethods(linesManager));
        }
      } else {
        log('❌ linesManager not found in context');
      }
    } catch (e) {
      log('⚠️ Error accessing linesManager:', e);
    }
    
    // Try to access document service
    try {
      const document = ctx.document;
      if (document) {
        log('✅ Found document service:', document.constructor?.name);
        if (detailedInspection) {
          log('Document methods:', getMethods(document).slice(0, 10));
        }
      }
    } catch (e) {
      log('⚠️ Error accessing document:', e);
    }
    
    // Try to access playground
    try {
      const playground = ctx.playground;
      if (playground) {
        log('✅ Found playground:', playground.constructor?.name);
        if (detailedInspection) {
          log('Playground methods:', getMethods(playground).slice(0, 10));
        }
      }
    } catch (e) {
      log('⚠️ Error accessing playground:', e);
    }
    
    // Expose debug functions to window for manual testing
    if (debug) {
      (window as any).__CUSTOM_LINES_DEBUG__ = {
        inspectContext: () => inspectContext(ctx),
        getContext: () => ctx,
        ctx,
      };
      log('💡 Debug functions exposed: window.__CUSTOM_LINES_DEBUG__');
    }
    
    log('🔍 Plugin initialization complete. Create/edit lines to see more logs.');
  },
  
  onDispose(ctx) {
    console.log('[CustomLinesPlugin] 🧹 Plugin disposed');
    // Clean up debug functions
    try {
      delete (window as any).__CUSTOM_LINES_DEBUG__;
    } catch {}
  },
});
