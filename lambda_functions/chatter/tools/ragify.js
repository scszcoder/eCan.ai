/**
 * Tool handler: ragify
 * Ingest a document/file into the RAG index for later querying.
 */
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";

const lambda = new LambdaClient({});
const RAG_LAMBDA = process.env.RAG_LAMBDA || "rag-processor";

export async function ragify(toolInput) {
  const { s3_uri, file_name, doc_type, owner_id, collection } = toolInput;
  if (!s3_uri || !owner_id) {
    throw new Error("s3_uri and owner_id are required");
  }

  const payload = {
    action: "ragify",
    s3_uri,
    file_name: file_name || s3_uri.split("/").pop(),
    doc_type: doc_type || "auto",
    owner_id,
    collection: collection || "default",
  };

  const resp = await lambda.send(new InvokeCommand({
    FunctionName: RAG_LAMBDA,
    InvocationType: "RequestResponse",
    Payload: JSON.stringify(payload),
  }));

  const result = JSON.parse(new TextDecoder().decode(resp.Payload));
  return result.body ? JSON.parse(result.body) : result;
}
