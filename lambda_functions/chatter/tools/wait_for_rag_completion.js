/**
 * Tool handler: wait_for_rag_completion
 * Poll until an async RAG ingestion job completes.
 */
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";

const lambda = new LambdaClient({});
const RAG_LAMBDA = process.env.RAG_LAMBDA || "rag-processor";

export async function wait_for_rag_completion(toolInput) {
  const { job_id, timeout_seconds } = toolInput;
  if (!job_id) {
    throw new Error("job_id is required");
  }

  const maxWait = Math.min(timeout_seconds || 30, 45) * 1000; // cap at 45s for Lambda safety
  const pollInterval = 3000;
  const start = Date.now();

  while (Date.now() - start < maxWait) {
    const resp = await lambda.send(new InvokeCommand({
      FunctionName: RAG_LAMBDA,
      InvocationType: "RequestResponse",
      Payload: JSON.stringify({ action: "status", job_id }),
    }));

    const result = JSON.parse(new TextDecoder().decode(resp.Payload));
    const body = result.body ? JSON.parse(result.body) : result;

    if (body.status === "completed" || body.status === "failed") {
      return body;
    }

    await new Promise((r) => setTimeout(r, pollInterval));
  }

  return { status: "timeout", job_id, message: `Timed out after ${Math.round((Date.now() - start) / 1000)}s` };
}
