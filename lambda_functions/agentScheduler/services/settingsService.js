/**
 * DynamoDB-based Settings Service for agentScheduler Lambda
 *
 * Uses ECAN_Settings table:
 *   PK: owner_id  (String) – normalised email, e.g. "songc_yahoo_com"
 *   SK: sid        (String) – random settings id, e.g. "set-a1b2c3d4"
 *   general_settings      (S) – JSON string
 *   llm_providers         (S) – JSON string
 *   embedding_providers   (S) – JSON string
 *   rerank_providers      (S) – JSON string
 *   created_at            (S) – ISO timestamp
 *   updated_at            (S) – ISO timestamp
 */

const crypto = require("crypto");
const {
  DynamoDBClient,
  PutItemCommand,
  QueryCommand,
} = require("@aws-sdk/client-dynamodb");
const { marshall, unmarshall } = require("@aws-sdk/util-dynamodb");

const REGION = process.env.AWS_REGION || "us-east-1";
const SETTINGS_TABLE = process.env.SETTINGS_TABLE || "ECAN_Settings";

const dynamodb = new DynamoDBClient({ region: REGION });

/**
 * Generate a random settings ID
 */
function genSid() {
  return `set-${crypto.randomBytes(4).toString("hex")}`;
}

/**
 * Safe JSON parse helper
 */
function safeParse(str) {
  if (!str) return {};
  if (typeof str === "object") return str;
  try {
    return JSON.parse(str);
  } catch {
    return {};
  }
}

/**
 * Convert DynamoDB item to normalised settings object
 */
function dbItemToSettings(item) {
  if (!item) return null;
  return {
    owner_id: item.owner_id,
    sid: item.sid,
    settings: safeParse(item.general_settings),
    llm_providers: safeParse(item.llm_providers),
    embedding_providers: safeParse(item.embedding_providers),
    rerank_providers: safeParse(item.rerank_providers),
    created_at: item.created_at,
    updated_at: item.updated_at,
  };
}

/**
 * Get settings for a given owner.
 * Returns the first (and typically only) settings record.
 *
 * @param {string} ownerId – normalised email e.g. "songc_yahoo_com"
 * @returns {object|null}
 */
async function getSettingsByOwner(ownerId) {
  const params = {
    TableName: SETTINGS_TABLE,
    KeyConditionExpression: "owner_id = :oid",
    ExpressionAttributeValues: marshall({ ":oid": ownerId }),
    Limit: 1,
  };

  const result = await dynamodb.send(new QueryCommand(params));
  if (!result.Items || result.Items.length === 0) return null;

  const raw = unmarshall(result.Items[0]);
  return dbItemToSettings(raw);
}

/**
 * Create or update (upsert) settings for a given owner.
 *
 * @param {string}  ownerId     – normalised email
 * @param {object}  payload     – { settings, llm_providers, embedding_providers, rerank_providers }
 * @param {string} [existingSid] – if provided, overwrites that sid; otherwise generates new
 * @returns {{ sid: string }}
 */
async function upsertSettings(ownerId, payload, existingSid) {
  const sid = existingSid || genSid();
  const now = new Date().toISOString();

  const item = {
    owner_id: ownerId,
    sid,
    general_settings:
      typeof payload.settings === "string"
        ? payload.settings
        : JSON.stringify(payload.settings || {}),
    llm_providers:
      typeof payload.llm_providers === "string"
        ? payload.llm_providers
        : JSON.stringify(payload.llm_providers || {}),
    embedding_providers:
      typeof payload.embedding_providers === "string"
        ? payload.embedding_providers
        : JSON.stringify(payload.embedding_providers || {}),
    rerank_providers:
      typeof payload.rerank_providers === "string"
        ? payload.rerank_providers
        : JSON.stringify(payload.rerank_providers || {}),
    updated_at: now,
  };

  // Only set created_at when creating new
  if (!existingSid) {
    item.created_at = now;
  }

  await dynamodb.send(
    new PutItemCommand({
      TableName: SETTINGS_TABLE,
      Item: marshall(item, { removeUndefinedValues: true }),
    })
  );

  return { sid };
}

module.exports = {
  getSettingsByOwner,
  upsertSettings,
};
