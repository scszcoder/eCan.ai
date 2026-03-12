/**
 * A2UISurface - React wrapper for A2UI Lit Surface
 * 
 * This component integrates A2UI Lit web components with React,
 * allowing dynamic form rendering from A2UI messages.
 */

import React, { useEffect, useRef, useCallback, useState } from 'react';
import styled from 'styled-components';

import type { A2UIServerMessage } from './types';

// Dynamic import of @a2ui/lit — the package may not be installed.
// We store the resolved module in a module-level variable so it's loaded once.
let _v0_8: any = null;
let _a2uiLoadAttempted = false;
let _a2uiLoadPromise: Promise<boolean> | null = null;

const loadA2UI = (): Promise<boolean> => {
  if (_a2uiLoadPromise) return _a2uiLoadPromise;
  // Use variable-based dynamic import so Vite's static analysis doesn't try
  // to resolve the specifier at pre-transform time (the package may not exist).
  const litPkg = '@a2ui/lit';
  const litUi = '@a2ui/lit/ui';
  _a2uiLoadPromise = (async () => {
    try {
      const mod = await (Function('p', 'return import(p)')(litPkg)) as any;
      await (Function('p', 'return import(p)')(litUi));
      _v0_8 = mod.v0_8;
      _a2uiLoadAttempted = true;
      return true;
    } catch {
      console.warn('[A2UISurface] @a2ui/lit not available — A2UI rendering disabled');
      _a2uiLoadAttempted = true;
      return false;
    }
  })();
  return _a2uiLoadPromise;
};

const createProcessor = () => _v0_8?.Data?.createSignalA2uiMessageProcessor?.() ?? null;

interface A2UISurfaceProps {
  /** A2UI messages to render */
  messages: A2UIServerMessage[];
  /** Callback when user triggers an action */
  onAction?: (actionName: string, context: Record<string, unknown>) => void;
  /** Surface ID to render (if multiple surfaces) */
  surfaceId?: string;
  /** Theme overrides */
  theme?: {
    primaryColor?: string;
  };
  /** Additional className */
  className?: string;
}

const SurfaceContainer = styled.div<{ $primaryColor?: string }>`
  /* A2UI surface container styling */
  --p-50: ${props => props.$primaryColor || '#3b82f6'};
  --p-40: color-mix(in srgb, var(--p-50) 80%, black 20%);
  --p-60: color-mix(in srgb, var(--p-50) 80%, white 20%);
  --p-30: color-mix(in srgb, var(--p-50) 60%, black 40%);
  --p-70: color-mix(in srgb, var(--p-50) 60%, white 40%);
  
  /* Dark theme defaults matching skill editor */
  --n-0: #000000;
  --n-10: #1e293b;
  --n-20: #334155;
  --n-90: #e2e8f0;
  --n-95: #f1f5f9;
  --n-100: #ffffff;
  
  /* MD3 color tokens */
  --md-sys-color-primary: var(--p-50);
  --md-sys-color-surface: var(--n-10);
  --md-sys-color-surface-container-low: var(--n-20);
  --md-sys-color-on-surface: var(--n-90);
  --md-sys-color-outline-variant: rgba(148, 163, 184, 0.3);
  
  /* Font */
  --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  
  font-family: var(--font-family);
  color: var(--n-90);
  
  /* Surface styling */
  a2ui-surface {
    display: block;
    width: 100%;
  }
  
  /* Component tweaks for dark theme */
  a2ui-text {
    color: var(--n-90);
  }
  
  a2ui-button {
    --md-sys-color-primary: var(--p-50);
    --md-sys-color-on-primary: var(--n-100);
  }
  
  a2ui-multiplechoice {
    --md-sys-color-surface: var(--n-20);
    --md-sys-color-on-surface: var(--n-90);
  }
  
  a2ui-textfield {
    --md-sys-color-surface: var(--n-20);
    --md-sys-color-on-surface: var(--n-90);
  }
`;

/**
 * A2UISurface component
 * 
 * Renders A2UI messages using the Lit renderer inside React.
 */
export const A2UISurface: React.FC<A2UISurfaceProps> = ({
  messages,
  onAction,
  surfaceId,
  theme,
  className,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const processorRef = useRef<ReturnType<typeof createProcessor> | null>(null);
  const [surfaces, setSurfaces] = useState<Map<string, any>>(new Map());
  const [a2uiReady, setA2uiReady] = useState(!!_v0_8);

  // Load @a2ui/lit dynamically on mount
  useEffect(() => {
    if (_v0_8) { setA2uiReady(true); return; }
    let cancelled = false;
    loadA2UI().then(ok => { if (!cancelled) setA2uiReady(ok); });
    return () => { cancelled = true; };
  }, []);

  // Initialize processor once library is ready
  useEffect(() => {
    if (!a2uiReady) return;
    processorRef.current = createProcessor();
    return () => {
      processorRef.current = null;
    };
  }, [a2uiReady]);

  // Process messages when they change
  useEffect(() => {
    const processor = processorRef.current;
    if (!processor || messages.length === 0) return;

    console.log('[A2UISurface] Processing messages:', messages.length);
    
    // Clear existing surfaces and process new messages
    processor.clearSurfaces();
    
    // Cast messages to the expected type
    processor.processMessages(messages as unknown as any[]);
    
    // Update React state with surfaces
    setSurfaces(new Map(processor.getSurfaces()));
  }, [messages, a2uiReady]);

  // Handle A2UI action events
  const handleAction = useCallback((evt: CustomEvent) => {
    console.log('[A2UISurface] Action received:', evt.detail);
    
    if (!onAction) return;
    
    const detail = evt.detail as {
      action: { name: string; context?: Array<{ key: string; value: unknown }> };
      sourceComponent?: string;
      dataContextPath?: string;
    };
    
    const actionName = detail.action?.name;
    if (!actionName) return;
    
    // Extract context values
    const context: Record<string, unknown> = {};
    const processor = processorRef.current;
    
    if (detail.action.context && processor) {
      for (const item of detail.action.context) {
        const itemValue = item.value as {
          literalBoolean?: boolean;
          literalNumber?: number;
          literalString?: string;
          path?: string;
        };
        
        if (itemValue.literalBoolean !== undefined) {
          context[item.key] = itemValue.literalBoolean;
        } else if (itemValue.literalNumber !== undefined) {
          context[item.key] = itemValue.literalNumber;
        } else if (itemValue.literalString !== undefined) {
          context[item.key] = itemValue.literalString;
        } else if (itemValue.path) {
          // Resolve path from data model
          const resolvedPath = processor.resolvePath(
            itemValue.path,
            detail.dataContextPath
          );
          const value = processor.getData(
            detail.sourceComponent || '',
            resolvedPath,
            surfaceId || ''
          );
          context[item.key] = value;
        }
      }
    }
    
    onAction(actionName, context);
  }, [onAction, surfaceId]);

  // Set up event listener on container
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.addEventListener('a2uiaction', handleAction as EventListener);
    return () => {
      container.removeEventListener('a2uiaction', handleAction as EventListener);
    };
  }, [handleAction]);

  // Render surfaces
  const renderSurfaces = () => {
    const processor = processorRef.current;
    if (!processor) return null;

    const surfaceEntries = Array.from(surfaces.entries());
    
    // Filter to specific surface if provided
    const filteredSurfaces = surfaceId
      ? surfaceEntries.filter(([id]) => id === surfaceId)
      : surfaceEntries;

    if (filteredSurfaces.length === 0) {
      return null;
    }

    return filteredSurfaces.map(([id, surface]) => {
      // Create the a2ui-surface element using React's createElement with ref
      // We need to use dangerouslySetInnerHTML or create the element imperatively
      return (
        <a2ui-surface
          key={id}
          // @ts-expect-error - Lit element properties
          surfaceId={id}
          surface={surface}
          processor={processor}
        />
      );
    });
  };

  if (!a2uiReady) {
    return (
      <div style={{ color: 'rgba(148,163,184,0.6)', fontSize: 12, padding: 8 }}>
        {_a2uiLoadAttempted ? 'A2UI renderer not available' : 'Loading A2UI\u2026'}
      </div>
    );
  }

  return (
    <SurfaceContainer
      ref={containerRef}
      className={className}
      $primaryColor={theme?.primaryColor}
    >
      {renderSurfaces()}
    </SurfaceContainer>
  );
};

// Declare custom element types for TypeScript
declare global {
  namespace JSX {
    interface IntrinsicElements {
      'a2ui-surface': React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          surfaceId?: string;
          surface?: any;
          processor?: any;
        },
        HTMLElement
      >;
    }
  }
}
