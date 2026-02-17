/**
 * Tool handler: ragify_async
 * Kick off an async RAG ingestion job (returns immediately with a job_id).
 */
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";

const lambda = new LambdaClient({});
const RAG_LAMBDA = process.env.RAG_LAMBDA || "rag-processor";

export async function ragify_async(toolInput) {
  const { s3_uri, file_name, doc_type, owner_id, collection } = toolInput;
  if (!s3_uri || !owner_id) {
    throw new Error("s3_uri and owner_id are required");
  }

  const payload = {
    action: "ragify_async",
    s3_uri,
    file_name: file_name || s3_uri.split("/").pop(),
    doc_type: doc_type || "auto",
    owner_id,
    collection: collection || "default",
  };

  const resp = await lambda.send(new InvokeCommand({
    FunctionName: RAG_LAMBDA,
    InvocationType: "Event", // async invocation
    Payload: JSON.stringify(payload),
  }));

  return {
    status: "submitted",
    job_id: payload.file_name, // use file_name as job_id for polling
    message: "RAG ingestion started asynchronously. Use wait_for_rag_completion to poll status.",
  };
}
