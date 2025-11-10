/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger, WorkflowLinesManager, useService } from '@flowgram.ai/free-layout-editor';
import React from 'react';
import { useNodeRenderContext } from '../../hooks';
import { autoRenameRefEffect } from '@flowgram.ai/form-materials';

import { FlowNodeJSON } from '../../typings';
import { FormHeader, FormContent } from '../../form-components';
import { ConditionInputs } from './condition-inputs';

export const renderForm = ({ form }: FormRenderProps<FlowNodeJSON>) => (
  <>
    <FormHeader />
    <FormContent>
      <ConditionInputs />
    </FormContent>
    <ConditionPortMarkers />
  </>
);

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: renderForm,
  validateTrigger: ValidateTrigger.onChange,
  validate: {
    title: ({ value }: { value: string }) => (value ? undefined : 'Title is required'),
    'conditions.*': ({ value }) => {
      const key: string | undefined = value?.key;
      const isElse = typeof key === 'string' && key.startsWith('else_');
      if (isElse) return undefined;
      if (!value?.value) return 'Condition is required';
      return undefined;
    },
  },
  effect: {
    conditions: autoRenameRefEffect,
  },
};

// Condition output markers positioned by live port side (location)
const ConditionPortMarkers: React.FC = () => {
  const { ports, node, form } = useNodeRenderContext();
  const linesMgr = useService(WorkflowLinesManager);
  const markerIfRef = React.useRef<HTMLDivElement>(null);
  const markerElseRef = React.useRef<HTMLDivElement>(null);
  
  // Read hFlip from multiple sources (form state, raw data, json)
  const hFlip = React.useMemo(() => {
    try {
      const fromForm = (form as any)?.state?.values?.data?.hFlip;
      if (typeof fromForm === 'boolean') return fromForm;
    } catch {}
    try {
      const fromRaw = (node as any)?.raw?.data?.hFlip;
      if (typeof fromRaw === 'boolean') return fromRaw;
    } catch {}
    try {
      const fromJson = (node as any)?.json?.data?.hFlip;
      if (typeof fromJson === 'boolean') return fromJson;
    } catch {}
    return false;
  }, [form, node]);
  
  const common: React.CSSProperties = {
    position: 'absolute',
    width: 14,
    height: 14,
    background: 'var(--g-workflow-port-color-primary)',
    cursor: 'crosshair',
    pointerEvents: 'auto',
    zIndex: 250,
    transform: 'translate(0, -50%)',
  };
  const rightClip = 'polygon(100% 50%, 0 0, 0 100%)';
  const leftClip = 'polygon(0 50%, 100% 0, 100% 100%)';

  const getLoc = (key: 'if_out' | 'else_out'): 'left' | 'right' => {
    // Always use hFlip state as the source of truth for marker positioning
    return hFlip ? 'left' : 'right';
  };

  const getPort = (key: 'if_out' | 'else_out') => {
    try {
      return (ports as any[] || []).find((pp: any) => {
        const pid: string = pp?.id || '';
        const pkey: string | undefined = pp?.portID ?? pp?.portId;
        return (pkey === key) || pid.endsWith(`_${key}`) || pid.includes(`_${key}_`) || pid.includes(key);
      });
    } catch { return undefined; }
  };

  const styleFor = (key: 'if_out' | 'else_out', fallbackTop: number): React.CSSProperties => {
    const p: any = getPort(key);
    const loc = (p?.location ?? p?.position) as ('left' | 'right' | undefined);
    // Always use fallback positioning to prevent overlap
    const top = fallbackTop;
    return {
      ...common,
      top,
      clipPath: loc === 'left' ? leftClip : rightClip,
      ...(loc === 'left' ? { left: -6, right: 'auto' } : { right: -6, left: 'auto' }),
    } as React.CSSProperties;
  };

  // Bind ports to their markers on mount and when ports/hFlip change
  React.useEffect(() => {
    // Use setTimeout to ensure markers are in DOM
    const timer = setTimeout(() => {
      try {
        const pIf = getPort('if_out');
        const pElse = getPort('else_out');
        const markerIf = markerIfRef.current;
        const markerElse = markerElseRef.current;
        
        // Restore port locations from hFlip state
        const targetLoc = hFlip ? 'left' : 'right';
        if (pIf) {
          const currentLoc = (pIf as any)?.location ?? (pIf as any)?.position;
          if (currentLoc !== targetLoc) {
            if (typeof (pIf as any).update === 'function') {
              (pIf as any).update({ location: targetLoc });
            }
          }
        }
        if (pElse) {
          const currentLoc = (pElse as any)?.location ?? (pElse as any)?.position;
          if (currentLoc !== targetLoc) {
            if (typeof (pElse as any).update === 'function') {
              (pElse as any).update({ location: targetLoc });
            }
          }
        }
        
        // Bind ports to markers
        if (pIf && markerIf) {
          if (typeof (pIf as any).setTargetElement === 'function') (pIf as any).setTargetElement(markerIf);
          else if (typeof (pIf as any).update === 'function') (pIf as any).update({ targetElement: markerIf });
        }
        if (pElse && markerElse) {
          if (typeof (pElse as any).setTargetElement === 'function') (pElse as any).setTargetElement(markerElse);
          else if (typeof (pElse as any).update === 'function') (pElse as any).update({ targetElement: markerElse });
        }
        // Force lines to update after rebinding
        try { (linesMgr as any)?.forceUpdate?.(); } catch {}
      } catch {}
    }, 0);
    return () => clearTimeout(timer);
  }, [ports, node.id, linesMgr, hFlip]);

  return (
    <>
      <div
        ref={markerIfRef}
        className="se-cond-port"
        data-port-id="if_out"
        data-port-type="output"
        data-port-direction="output"
        data-port-group="conditions"
        data-port-name="if_out"
        data-port="true"
        style={styleFor('if_out', 50)}
        title="if"
      />
      <div
        ref={markerElseRef}
        className="se-cond-port"
        data-port-id="else_out"
        data-port-type="output"
        data-port-direction="output"
        data-port-group="conditions"
        data-port-name="else_out"
        data-port="true"
        style={styleFor('else_out', 90)}
        title="else"
      />
    </>
  );
};
