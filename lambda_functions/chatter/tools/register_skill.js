/**
 * Tool handler: register_skill
 * Register a new skill in the skill registry.
 */
import { DynamoDBClient, PutItemCommand } from "@aws-sdk/client-dynamodb";
import { marshall } from "@aws-sdk/util-dynamodb";
import { randomUUID } from "node:crypto";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const SKILLS_TABLE = process.env.SKILLS_TABLE || "Skills";

export async function register_skill(toolInput) {
  const { owner_id, name, category, description, input_schema, output_schema, triggers, nodes } = toolInput;
  if (!owner_id || !name || !category) {
    throw new Error("owner_id, name, and category are required");
  }

  const skillId = randomUUID();
  const now = new Date().toISOString();
  const item = {
    owner_id,
    skill_id: skillId,
    name,
    category,
    description: description || "",
    input_schema: input_schema || {},
    output_schema: output_schema || {},
    triggers: triggers || [],
    nodes: nodes || [],
    status: "active",
    created_at: now,
    updated_at: now,
  };

  await dynamodb.send(new PutItemCommand({
    TableName: SKILLS_TABLE,
    Item: marshall(item, { removeUndefinedValues: true }),
  }));

  return { skill_id: skillId, name, category, status: "registered", created_at: now };
}
