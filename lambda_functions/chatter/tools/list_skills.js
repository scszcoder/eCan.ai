/**
 * Tool handler: list_skills
 * List all available skills and their statuses.
 */
import { DynamoDBClient, QueryCommand } from "@aws-sdk/client-dynamodb";
import { unmarshall } from "@aws-sdk/util-dynamodb";

const dynamodb = new DynamoDBClient({ region: "us-east-1" });
const SKILLS_TABLE = process.env.SKILLS_TABLE || "Skills";

export async function list_skills(toolInput) {
  const { owner_id, category, status_filter } = toolInput;
  if (!owner_id) {
    throw new Error("owner_id is required");
  }

  const resp = await dynamodb.send(new QueryCommand({
    TableName: SKILLS_TABLE,
    KeyConditionExpression: "owner_id = :oid",
    ExpressionAttributeValues: { ":oid": { S: owner_id } },
  }));

  let skills = (resp.Items || []).map(item => unmarshall(item));

  if (category) {
    skills = skills.filter(s => s.category === category);
  }
  if (status_filter && status_filter !== "all") {
    skills = skills.filter(s => s.status === status_filter);
  }

  return { skills, count: skills.length };
}
