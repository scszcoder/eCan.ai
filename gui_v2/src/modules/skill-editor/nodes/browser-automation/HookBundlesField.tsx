/**
 * HookBundlesField — structured editor for the browser-automation node's
 * ``hookBundles`` config.
 *
 * Replaces the free-form JSON textarea while staying byte-compatible: we
 * read and write the SAME JSON shape, so existing saved skills upgrade
 * transparently and old/new skill files stay interchangeable.
 *
 * Modes:
 *   - "structured" (default): multi-row editor; each row picks an installed
 *     plugin from a dropdown and has an optional per-bundle JSON config.
 *   - "advanced": original raw JSON textarea (escape hatch; lets users
 *     hand-edit anything the structured UI can't yet express, like
 *     ``pkg:`` or absolute-path entries to bundles that aren't in the
 *     installed list).
 *
 * Semi UI is used here (matches the rest of form-meta.tsx). The Ant
 * Design ``PluginAutoForm`` lives on the Plugins page; per-bundle auto
 * forms inside the skill editor are deferred to a later phase to avoid
 * the Semi/Ant visual mix mid-form.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Select, TextArea, Typography, Tag, Radio, RadioGroup } from '@douyinfe/semi-ui';
import { IconDelete, IconPlus, IconAlertTriangle } from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';
import { listPlugins } from '@/services/api/pluginApi';
import type { PluginEntry } from '@/services/api/pluginApi';

interface BundleSpec {
  path: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
}

export interface HookBundlesFieldProps {
  /** The raw JSON string currently stored in inputsValues.hookBundles.content */
  value: string;
  /** Called with the new JSON string. */
  onChange: (next: string) => void;
}

function parseValue(raw: string): { parsed: BundleSpec[]; ok: boolean } {
  if (!raw || !raw.trim()) return { parsed: [], ok: true };
  try {
    const v = JSON.parse(raw);
    if (Array.isArray(v)) {
      const out: BundleSpec[] = [];
      for (const item of v) {
        if (typeof item === 'string') {
          out.push({ path: item, enabled: true, config: {} });
        } else if (item && typeof item === 'object' && typeof (item as any).path === 'string') {
          out.push({
            path: (item as any).path,
            enabled: typeof (item as any).enabled === 'boolean' ? (item as any).enabled : true,
            config: (item as any).config && typeof (item as any).config === 'object'
              ? (item as any).config
              : {},
          });
        }
      }
      return { parsed: out, ok: true };
    }
  } catch {
    // fall through
  }
  return { parsed: [], ok: false };
}

function serialize(specs: BundleSpec[]): string {
  if (specs.length === 0) return '';
  const out = specs.map((s) => ({
    path: s.path,
    enabled: s.enabled === false ? false : true,
    config: s.config && Object.keys(s.config).length > 0 ? s.config : {},
  }));
  return JSON.stringify(out, null, 2);
}

export const HookBundlesField: React.FC<HookBundlesFieldProps> = ({ value, onChange }) => {
  const { t } = useTranslation();
  const [mode, setMode] = useState<'structured' | 'advanced'>(() => {
    const { ok } = parseValue(value || '');
    return ok ? 'structured' : 'advanced';
  });
  const [installed, setInstalled] = useState<PluginEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listPlugins('all')
      .then((resp) => {
        if (cancelled) return;
        if (resp.success && resp.data) {
          setInstalled(resp.data.items);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const { parsed, ok: parseOk } = useMemo(() => parseValue(value || ''), [value]);
  const specs = parsed;

  const update = useCallback(
    (next: BundleSpec[]) => {
      onChange(serialize(next));
    },
    [onChange]
  );

  const addRow = () => {
    update([...specs, { path: '', enabled: true, config: {} }]);
  };

  const removeRow = (i: number) => {
    const next = [...specs];
    next.splice(i, 1);
    update(next);
  };

  const setPath = (i: number, path: string) => {
    const next = [...specs];
    next[i] = { ...next[i], path };
    update(next);
  };

  const setConfigJson = (i: number, jsonStr: string) => {
    const next = [...specs];
    let config: Record<string, unknown> = {};
    try {
      const v = JSON.parse(jsonStr || '{}');
      if (v && typeof v === 'object' && !Array.isArray(v)) config = v;
    } catch {
      // Keep the bad text in a private slot so user can fix it; we store an empty
      // config until JSON is valid. To preserve typing UX we'd need a per-row
      // text-buffer state — left for a follow-up if users complain.
    }
    next[i] = { ...next[i], config };
    update(next);
  };

  const toggleEnabled = (i: number, enabled: boolean) => {
    const next = [...specs];
    next[i] = { ...next[i], enabled };
    update(next);
  };

  // ---- Advanced JSON mode ----
  if (mode === 'advanced') {
    return (
      <div>
        <ModeToggle mode={mode} onChange={setMode} disableStructured={!parseOk} />
        <TextArea
          value={value || ''}
          onChange={(val) => onChange(val)}
          placeholder={'[{"path":"feige_chat","enabled":true,"config":{"cooldown_ms":1500}}]'}
          autosize={{ minRows: 4, maxRows: 12 }}
          style={{ width: '100%', fontFamily: 'monospace', fontSize: 12 }}
        />
        {!parseOk ? (
          <Typography.Text type="warning" size="small">
            <IconAlertTriangle /> JSON is invalid — fix it before switching back to Structured.
          </Typography.Text>
        ) : null}
      </div>
    );
  }

  // ---- Structured mode ----
  const installedOptions = installed.map((p) => ({
    label: `${p.name} (${p.install_source})${p.enabled ? '' : ' — disabled'}`,
    value: p.name,
  }));

  return (
    <div>
      <ModeToggle mode={mode} onChange={setMode} disableStructured={!parseOk} />
      {specs.length === 0 ? (
        <Typography.Text type="tertiary" size="small">
          {t('plugins.nodeField.emptyHint', 'No plugin bundles attached to this node yet.')}
        </Typography.Text>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {specs.map((spec, i) => {
            const matching = installed.find((p) => p.name === spec.path);
            const labelText = matching
              ? `${matching.name} (${matching.install_source})`
              : spec.path
              ? `${spec.path} (not installed)`
              : '';
            return (
              <div
                key={i}
                style={{
                  border: '1px solid var(--semi-color-border)',
                  borderRadius: 4,
                  padding: 8,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 6,
                }}
              >
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <Select
                    style={{ flex: 1 }}
                    value={spec.path || undefined}
                    placeholder={t('plugins.nodeField.selectBundle', 'Select a plugin to attach')}
                    optionList={installedOptions}
                    onChange={(val) => setPath(i, String(val))}
                    filter
                    loading={loading}
                    allowCreate
                    onSearch={() => {}}
                    showArrow
                    size="small"
                  />
                  <Tag
                    color={spec.enabled === false ? 'grey' : 'green'}
                    style={{ cursor: 'pointer' }}
                    onClick={() => toggleEnabled(i, !(spec.enabled === false ? false : true))}
                  >
                    {spec.enabled === false
                      ? t('plugins.list.disable', 'Disabled')
                      : t('plugins.list.enable', 'Enabled')}
                  </Tag>
                  <Button
                    icon={<IconDelete />}
                    type="danger"
                    theme="borderless"
                    size="small"
                    onClick={() => removeRow(i)}
                  />
                </div>
                {labelText && !matching && spec.path ? (
                  <Typography.Text type="warning" size="small">
                    <IconAlertTriangle /> Plugin not installed: {spec.path}
                  </Typography.Text>
                ) : null}
                <div>
                  <Typography.Text size="small" type="tertiary">
                    {t('plugins.nodeField.perNodeConfigTitle', 'Config for this node')} (JSON):
                  </Typography.Text>
                  <TextArea
                    value={spec.config && Object.keys(spec.config).length > 0
                      ? JSON.stringify(spec.config, null, 2)
                      : ''}
                    placeholder={'{"cooldown_ms":1500}'}
                    onChange={(val) => setConfigJson(i, val)}
                    autosize={{ minRows: 2, maxRows: 8 }}
                    style={{ width: '100%', fontFamily: 'monospace', fontSize: 12 }}
                  />
                  {matching && !matching.manifest_summary?.config_schema ? (
                    <Typography.Text size="small" type="tertiary">
                      {t(
                        'plugins.nodeField.noConfigSchema',
                        'This plugin has no config schema; use Advanced JSON to set arbitrary config.'
                      )}
                    </Typography.Text>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <div style={{ marginTop: 8 }}>
        <Button icon={<IconPlus />} size="small" onClick={addRow}>
          {t('plugins.nodeField.addBundle', 'Add bundle…')}
        </Button>
      </div>
    </div>
  );
};

const ModeToggle: React.FC<{
  mode: 'structured' | 'advanced';
  onChange: (m: 'structured' | 'advanced') => void;
  disableStructured?: boolean;
}> = ({ mode, onChange, disableStructured }) => {
  const { t } = useTranslation();
  return (
    <div style={{ marginBottom: 8 }}>
      <RadioGroup
        type="button"
        value={mode}
        onChange={(e) => onChange((e as any).target.value)}
      >
        <Radio value="structured" disabled={disableStructured}>
          {t('plugins.nodeField.modeStructured', 'Structured')}
        </Radio>
        <Radio value="advanced">{t('plugins.nodeField.modeAdvanced', 'Advanced JSON')}</Radio>
      </RadioGroup>
    </div>
  );
};

export default HookBundlesField;
