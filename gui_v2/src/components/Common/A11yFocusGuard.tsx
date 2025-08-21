/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React from 'react';

/**
 * Global focus guard to avoid "Blocked aria-hidden on an element because its descendant retained focus".
 * - When any element gets aria-hidden=true while containing the activeElement, we blur and move focus safely.
 */
export const A11yFocusGuard: React.FC = () => {
  React.useEffect(() => {
    if (typeof MutationObserver === 'undefined') return;

    const moveFocusToSafeTarget = () => {
      // Try to move to the document body as a last resort
      if (document && document.body && typeof (document.body as any).focus === 'function') {
        (document.body as HTMLElement).focus();
      }
    };

    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type !== 'attributes' || m.attributeName !== 'aria-hidden') continue;
        const target = m.target as HTMLElement;
        const hidden = target.getAttribute('aria-hidden') === 'true';
        if (!hidden) continue;
        const active = document.activeElement as HTMLElement | null;
        if (active && target.contains(active)) {
          // Move focus away from the hidden subtree
          try {
            active.blur();
          } catch {}
          moveFocusToSafeTarget();
        }
      }
    });

    try {
      observer.observe(document.body, { attributes: true, subtree: true, attributeFilter: ['aria-hidden'] });
    } catch {}

    return () => {
      observer.disconnect();
    };
  }, []);

  return null;
};

export default A11yFocusGuard;


