# Inbound Messaging — SMS & Email

Receives inbound SMS and email, routes by destination address (Option 1: per-user
addresses), and publishes a `publishIncomingMessage` GraphQL mutation against AppSync.
Clients subscribe via `onIncomingMessage(owner: String!)` over the existing
WebSocket subscription channel.

## DynamoDB routing table

```
TableName:    messaging_inbound_routing
PartitionKey: address           (String) — phone number (E.164) or email address
Attributes:
  owner       (String, required) — Cognito email / sub
  sessionId   (String, optional) — chat session to attach the message to
  channel     (String)           — "sms" | "email"
  createdAt   (String, ISO-8601)
```

Create with AWS CLI:

```bash
aws dynamodb create-table \
  --table-name messaging_inbound_routing \
  --attribute-definitions AttributeName=address,AttributeType=S \
  --key-schema AttributeName=address,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

Add a routing entry when allocating a number/address to a user:

```bash
aws dynamodb put-item \
  --table-name messaging_inbound_routing \
  --item '{
    "address":   {"S": "+18885550199"},
    "owner":     {"S": "user@example.com"},
    "sessionId": {"S": "sess_abc123"},
    "channel":   {"S": "sms"},
    "createdAt": {"S": "2026-05-03T00:00:00Z"}
  }'
```

## Inbound SMS plumbing (AWS End User Messaging SMS)

1. Provision an AWS End User Messaging SMS phone number with **two-way SMS** enabled.
2. In two-way config, set the destination type to **SNS topic** and create
   `messaging-inbound-sms` SNS topic.
3. Subscribe THIS Lambda to the SNS topic.
4. Add a row to `messaging_inbound_routing` mapping the allocated phone number → owner.

## Inbound email plumbing (SES Receipt Rule)

SES inbound only works in: us-east-1, us-west-2, eu-west-1.

1. Verify a domain in SES (e.g. `inbox.ecan.ai`) and add MX record per AWS docs.
2. Create an SES Receipt Rule Set with a rule that:
   - **Recipients**: addresses like `*@inbox.ecan.ai` (or per-user aliases).
   - **Action 1**: write to S3 (bucket: `INBOUND_EMAIL_S3_BUCKET`, prefix: `incoming/`).
   - **Action 2**: notify SNS topic `messaging-inbound-email`.
3. Subscribe THIS Lambda to the SNS topic.
4. Add a row to `messaging_inbound_routing` mapping the per-user email → owner.

## Lambda env vars

| Variable | Description |
|---|---|
| `APPSYNC_API_URL` | AppSync endpoint |
| `APPSYNC_API_KEY` | x-api-key for `publishIncomingMessage` |
| `MESSAGING_ROUTING_TABLE` | DynamoDB table (default: `messaging_inbound_routing`) |
| `INBOUND_EMAIL_S3_BUCKET` | bucket where SES stores raw email (only if S3 receipt rule used) |

## IAM policy (this Lambda)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["dynamodb:GetItem"],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/messaging_inbound_routing" },
    { "Effect": "Allow", "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::ecan-inbound-email/*" }
  ]
}
```

## Outbound (for reference) — agentScheduler messagingService

Outbound `sendEmail` (SES) and `sendSms` (AWS End User Messaging SMS) are exposed
via the agentScheduler GraphQL API. Required env vars on the agentScheduler Lambda:

| Variable | Description |
|---|---|
| `SES_FROM_EMAIL` | verified SES sender (e.g. `noreply@ecan.ai`) |
| `SMS_ORIGINATION_IDENTITY` | phone number ARN, pool ID, or registered sender ID |
| `SMS_CONFIGURATION_SET` | (optional) for delivery event logs |

IAM additions on the agentScheduler role:
- `ses:SendEmail`
- `sms-voice:SendTextMessage`
