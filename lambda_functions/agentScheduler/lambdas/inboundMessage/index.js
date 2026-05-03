/**
 * Inbound message handler — SMS and Email.
 *
 * This Lambda receives:
 *   1. SMS  — via SNS notification from AWS End User Messaging SMS two-way
 *             routing (the originating phone number's two-way config points
 *             to an SNS topic that this Lambda is subscribed to).
 *   2. Email — via SNS notification from an SES Receipt Rule that either
 *              publishes the parsed message directly, or stores the raw
 *              MIME in S3 and notifies SNS with the S3 key. Either path
 *              is supported below.
 *
 * Routing — Option 1 (per-user address): a DynamoDB table maps the user's
 *   allocated phone number / email address to their owner ID. This Lambda
 *   resolves the owner from the destination address, then publishes a
 *   `publishIncomingMessage` GraphQL mutation against AppSync. AppSync
 *   fans the event out to clients via the existing WebSocket subscription
 *   (`onIncomingMessage(owner: String!)`).
 *
 * Routing table — DynamoDB schema (see README):
 *   table: messaging_inbound_routing
 *     PK: address (String)        — phone number (E.164) or email address
 *     attrs:
 *       owner       (String)      — Cognito email / sub
 *       sessionId   (String, opt) — chat session to attach to
 *       channel     (String)      — "sms" | "email"
 *       createdAt   (String, ISO)
 *
 * Required env vars:
 *   APPSYNC_API_URL                    — e.g. https://...appsync-api.us-east-1.amazonaws.com/graphql
 *   APPSYNC_API_KEY                    — x-api-key for the publishIncomingMessage mutation
 *   MESSAGING_ROUTING_TABLE            — DynamoDB table name (default: messaging_inbound_routing)
 *   INBOUND_EMAIL_S3_BUCKET            — (optional) bucket where SES stores raw email (if S3 receipt rule)
 *
 * IAM permissions on this Lambda's role:
 *   dynamodb:GetItem on the routing table
 *   s3:GetObject    on the inbound email bucket (if used)
 *   (AppSync API key auth is HTTP-level; no IAM needed on the publish call)
 */

const { DynamoDBClient, GetItemCommand } = require("@aws-sdk/client-dynamodb");
const { S3Client, GetObjectCommand } = require("@aws-sdk/client-s3");

const REGION = process.env.AWS_REGION || "us-east-1";
const APPSYNC_API_URL = (process.env.APPSYNC_API_URL || "").trim();
const APPSYNC_API_KEY = (process.env.APPSYNC_API_KEY || "").trim();
const ROUTING_TABLE = (process.env.MESSAGING_ROUTING_TABLE || "messaging_inbound_routing").trim();

const ddb = new DynamoDBClient({ region: REGION });
const s3 = new S3Client({ region: REGION });

const PUBLISH_MUTATION = /* GraphQL */ `
  mutation PublishIncomingMessage($input: IncomingMessageInput!) {
    publishIncomingMessage(input: $input) {
      messageId
      owner
    }
  }
`;

async function lookupOwner(address) {
  if (!address) return null;
  try {
    const resp = await ddb.send(
      new GetItemCommand({
        TableName: ROUTING_TABLE,
        Key: { address: { S: String(address) } },
        ProjectionExpression: "#o, sessionId, channel",
        ExpressionAttributeNames: { "#o": "owner" },
      }),
    );
    if (!resp.Item) return null;
    return {
      owner: resp.Item.owner?.S || null,
      sessionId: resp.Item.sessionId?.S || null,
      channel: resp.Item.channel?.S || null,
    };
  } catch (e) {
    console.error(`[inboundMessage] DynamoDB lookup failed for ${address}: ${e.message}`);
    return null;
  }
}

async function publishToAppSync(payload) {
  if (!APPSYNC_API_URL || !APPSYNC_API_KEY) {
    throw new Error("APPSYNC_API_URL / APPSYNC_API_KEY not configured");
  }
  const body = {
    query: PUBLISH_MUTATION,
    variables: { input: payload },
  };
  const resp = await fetch(APPSYNC_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": APPSYNC_API_KEY,
    },
    body: JSON.stringify(body),
  });
  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`AppSync publish HTTP ${resp.status}: ${text}`);
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`AppSync publish non-JSON response: ${text}`);
  }
  if (parsed.errors) {
    throw new Error(`AppSync publish errors: ${JSON.stringify(parsed.errors)}`);
  }
  return parsed.data?.publishIncomingMessage;
}

// --- SMS handler (AWS End User Messaging SMS → SNS → this Lambda) ---
//
// SNS message body (parsed JSON):
//   {
//     originationNumber: "+14155550100",   // who sent the SMS to us
//     destinationNumber: "+18885550199",   // our allocated number
//     messageBody: "...",
//     messageKeyword: "DEFAULT",
//     inboundMessageId: "...",
//     previousPublishedMessageId: "...",
//   }
async function handleSmsRecord(snsBody) {
  const fromAddress = snsBody.originationNumber || snsBody.fromNumber;
  const toAddress = snsBody.destinationNumber || snsBody.toNumber;
  const body = snsBody.messageBody || snsBody.message || "";
  const messageId = snsBody.inboundMessageId || snsBody.messageId || `sms_${Date.now()}`;

  const route = await lookupOwner(toAddress);
  if (!route || !route.owner) {
    console.warn(
      `[inboundMessage] No routing for SMS to ${toAddress} — message dropped (from=${fromAddress})`,
    );
    return { dropped: true, reason: "no_routing", address: toAddress };
  }

  const payload = {
    messageId,
    channel: "sms",
    fromAddress,
    toAddress,
    body,
    owner: route.owner,
    sessionId: route.sessionId,
  };
  const published = await publishToAppSync(payload);
  console.log(
    `[inboundMessage] SMS routed — to=${toAddress}, owner=${route.owner}, messageId=${messageId}`,
  );
  return { published };
}

// --- Email handler ---
//
// SES → SNS publishes a record like:
//   {
//     notificationType: "Received",
//     mail: { destination: ["alias@inbox.ecan.ai"], source: "sender@example.com",
//             messageId: "...", commonHeaders: { subject: "..." } },
//     content: <raw MIME — only if SES action is "SNS-with-content">,
//     receipt: { action: { type, bucketName, objectKey } }
//   }
async function handleEmailRecord(sesNotification) {
  const mail = sesNotification.mail || {};
  const fromAddress = mail.source || (mail.commonHeaders?.from || [])[0] || "";
  const toAddress = (mail.destination || [])[0] || "";
  const subject = mail.commonHeaders?.subject || "";
  const messageId = mail.messageId || `email_${Date.now()}`;

  let body = "";
  // If SES delivered the raw content inline (small messages only):
  if (typeof sesNotification.content === "string" && sesNotification.content) {
    body = sesNotification.content;
  } else {
    // Otherwise SES stored it in S3 — fetch the raw MIME.
    const action = sesNotification.receipt?.action || {};
    if (action.type === "S3" && action.bucketName && action.objectKey) {
      try {
        const obj = await s3.send(
          new GetObjectCommand({ Bucket: action.bucketName, Key: action.objectKey }),
        );
        const chunks = [];
        for await (const chunk of obj.Body) chunks.push(chunk);
        body = Buffer.concat(chunks).toString("utf-8");
        // NB: `body` is raw MIME here. Real plain-text/HTML extraction needs
        // a parser like `mailparser`. For now we pass the raw MIME through;
        // the consuming agent or skill can extract what it needs.
      } catch (e) {
        console.error(`[inboundMessage] S3 fetch for raw email failed: ${e.message}`);
      }
    }
  }

  const route = await lookupOwner(toAddress);
  if (!route || !route.owner) {
    console.warn(
      `[inboundMessage] No routing for email to ${toAddress} — dropped (from=${fromAddress})`,
    );
    return { dropped: true, reason: "no_routing", address: toAddress };
  }

  const payload = {
    messageId,
    channel: "email",
    fromAddress,
    toAddress,
    body,
    subject,
    owner: route.owner,
    sessionId: route.sessionId,
  };
  const published = await publishToAppSync(payload);
  console.log(
    `[inboundMessage] Email routed — to=${toAddress}, owner=${route.owner}, messageId=${messageId}`,
  );
  return { published };
}

// --- Lambda entry point ---

exports.handler = async (event) => {
  const records = event.Records || [];
  const results = [];

  for (const record of records) {
    if (record.EventSource !== "aws:sns" && record.eventSource !== "aws:sns") continue;
    const sns = record.Sns || {};
    let parsed;
    try {
      parsed = JSON.parse(sns.Message || "{}");
    } catch (e) {
      console.warn(`[inboundMessage] SNS message is not JSON: ${sns.Message}`);
      results.push({ error: "non_json_sns_payload" });
      continue;
    }

    try {
      // Distinguish SMS vs Email by shape of the SNS payload.
      if (parsed.notificationType === "Received" || parsed.mail) {
        results.push(await handleEmailRecord(parsed));
      } else if (parsed.originationNumber || parsed.destinationNumber) {
        results.push(await handleSmsRecord(parsed));
      } else {
        console.warn(
          `[inboundMessage] Unknown SNS payload shape — keys=${Object.keys(parsed).join(",")}`,
        );
        results.push({ error: "unknown_payload_shape" });
      }
    } catch (e) {
      console.error(`[inboundMessage] Record handler failed: ${e.message}`);
      results.push({ error: e.message });
    }
  }

  return { processed: results.length, results };
};
