/**
 * Lightweight RDS Data API wrapper for chatter tool handlers.
 * Reuses the same connection pattern as agentScheduler.
 */
import { RDSDataClient, ExecuteStatementCommand } from "@aws-sdk/client-rds-data";

const REGION = process.env.AWS_REGION || "us-east-1";
const resourceArn = process.env.DBAuroraClusterArn;
const secretArn = process.env.DBSecretsStoreArn;
const database = process.env.DatabaseName;

const client = new RDSDataClient({ region: REGION });

/**
 * Execute a SQL statement via RDS Data API.
 * @param {string} sql - SQL statement with :named parameters
 * @param {Array} parameters - Array of { name, value: { stringValue|longValue|... } }
 * @returns {Promise<Object>} Raw RDS Data API response
 */
export async function execute(sql, parameters = []) {
  if (!resourceArn || !secretArn || !database) {
    throw new Error("RDS config missing: ensure DBAuroraClusterArn, DBSecretsStoreArn, and DatabaseName env vars are set");
  }
  const command = new ExecuteStatementCommand({
    resourceArn,
    secretArn,
    database,
    sql,
    parameters,
    includeResultMetadata: true,
  });
  return client.send(command);
}

/**
 * Helper to build a named string parameter.
 */
export function strParam(name, value) {
  if (value === null || value === undefined) {
    return { name, value: { isNull: true } };
  }
  return { name, value: { stringValue: String(value) } };
}

/**
 * Convert RDS Data API response rows into plain JS objects.
 */
export function rowsToObjects(result) {
  const cols = (result.columnMetadata || []).map(c => (c.name || "").toLowerCase());
  return (result.records || []).map(row => {
    const obj = {};
    cols.forEach((col, idx) => {
      const field = row[idx];
      if (!field) { obj[col] = null; return; }
      if (field.stringValue !== undefined) obj[col] = field.stringValue;
      else if (field.longValue !== undefined) obj[col] = field.longValue;
      else if (field.doubleValue !== undefined) obj[col] = field.doubleValue;
      else if (field.booleanValue !== undefined) obj[col] = field.booleanValue;
      else if (field.isNull) obj[col] = null;
      else obj[col] = null;
    });
    return obj;
  });
}
