import { useEffect, useState } from 'react';
import { IPCAPI } from '../services/ipc/api';

export type JSONSchema = Record<string, any>;

let cachedSchema: JSONSchema | null = null;
let cachedVersion: string | null = null;
let loadingPromise: Promise<{ schema: JSONSchema; schemaVersion: string }> | null = null;

export async function loadNodeStateSchema(): Promise<{ schema: JSONSchema; schemaVersion: string }> {
  if (cachedSchema && cachedVersion) return { schema: cachedSchema, schemaVersion: cachedVersion };
  if (!loadingPromise) {
    loadingPromise = (async () => {
      const api = IPCAPI.getInstance();
      const resp = await api.getNodeStateSchema<{ schemaVersion: string; schema: JSONSchema }>();
      if (resp.success && resp.data) {
        cachedSchema = resp.data.schema;
        cachedVersion = resp.data.schemaVersion;
        return { schema: cachedSchema, schemaVersion: cachedVersion } as any;
      }
      // Fallback minimal schema
      const fallback = {
        $schema: 'http://json-schema.org/draft-07/schema#',
        title: 'NodeState',
        type: 'object',
        properties: {},
        additionalProperties: true,
      } as JSONSchema;
      cachedSchema = fallback;
      cachedVersion = 'fallback';
      return { schema: cachedSchema, schemaVersion: cachedVersion };
    })();
  }
  const res = await loadingPromise;
  loadingPromise = null;
  return res;
}

export function useNodeStateSchema() {
  const [schema, setSchema] = useState<JSONSchema | null>(cachedSchema);
  const [version, setVersion] = useState<string | null>(cachedVersion);
  const [loading, setLoading] = useState(!cachedSchema);

  useEffect(() => {
    let mounted = true;
    if (!cachedSchema) {
      setLoading(true);
      loadNodeStateSchema()
        .then(({ schema, schemaVersion }) => {
          if (!mounted) return;
          setSchema(schema);
          setVersion(schemaVersion);
        })
        .finally(() => mounted && setLoading(false));
    }
    return () => {
      mounted = false;
    };
  }, []);

  return { schema, version, loading } as const;
}
