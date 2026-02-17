/**
 * Tool handler: rag_query
 * Query the RAG index for relevant documents.
 */
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";

const lambda = new LambdaClient({});
const RAG_LAMBDA = process.env.RAG_LAMBDA || "rag-processor";

export async function rag_query(toolInput) {
  const { query, top_k, owner_id, collection, filters } = toolInput;
  if (!query || !owner_id) {
    throw new Error("query and owner_id are required");
  }

  const payload = {
    action: "query",
    query,
    top_k: top_k || 5,
    owner_id,
    collection: collection || "default",
    filters: filters || {},
  };

  const resp = await lambda.send(new InvokeCommand({
    FunctionName: RAG_LAMBDA,
    InvocationType: "RequestResponse",
    Payload: JSON.stringify(payload),
  }));

  const result = JSON.parse(new TextDecoder().decode(resp.Payload));
  return result.body ? JSON.parse(result.body) : result;
}
