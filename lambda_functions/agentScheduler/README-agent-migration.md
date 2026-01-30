# Agent DB/AppSync migration guide

This Lambda now uses `services/agentService.js` + the MySQL schema in `schema/agents.sql`. Follow these steps to deploy.

## 1) Apply MySQL schema to RDS (Aurora/MySQL)
Prereqs: `DBAuroraClusterArn`, `DBSecretsStoreArn`, `DatabaseName`, and a DB user with CREATE TABLE.

- Using the Data API (Aurora Serverless):
  ```bash
  aws rds-data execute-statement \
    --resource-arn "$DBAuroraClusterArn" \
    --secret-arn "$DBSecretsStoreArn" \
    --database "$DatabaseName" \
    --sql "$(cat schema/agents.sql)"
  ```
- Or via mysql client:
  ```bash
  mysql -h <rds-endpoint> -u <user> -p<pass> <DatabaseName> < schema/agents.sql
  ```

## 2) Update AppSync schema
```bash
aws appsync start-schema-creation \
  --api-id <API_ID> \
  --definition fileb://graphql/agent.graphql
```

## 3) Attach resolvers to this Lambda
For each field below, create/update a Lambda resolver with the matching VTL files:

| Field                                | Request VTL                                      | Response VTL                                     |
| ------------------------------------ | ------------------------------------------------ | ------------------------------------------------ |
| Mutation.addAgents                   | graphql/resolvers/Mutation.addAgents.request.vtl | graphql/resolvers/Mutation.addAgents.response.vtl |
| Mutation.updateAgents                | graphql/resolvers/Mutation.updateAgents.request.vtl | graphql/resolvers/Mutation.updateAgents.response.vtl |
| Mutation.removeAgents                | graphql/resolvers/Mutation.removeAgents.request.vtl | graphql/resolvers/Mutation.removeAgents.response.vtl |
| Mutation.updateStory                 | *(direct Lambda resolver – see below)*           | *(direct Lambda resolver – see below)*           |
| Query.getAgents                      | graphql/resolvers/Query.getAgents.request.vtl    | graphql/resolvers/Query.getAgents.response.vtl   |
| Query.queryAgents                    | graphql/resolvers/Query.queryAgents.request.vtl  | graphql/resolvers/Query.queryAgents.response.vtl |

### Python resolver for `updateStory`

The Lambda entry point for the story mutation lives in [lambdas/story_updater/app.py](lambdas/story_updater/app.py). Package and deploy it separately from the Node runtime:

```bash
zip -j build/update-story.zip lambdas/story_updater/app.py
aws lambda update-function-code \
  --function-name <UpdateStoryLambdaName> \
  --zip-file fileb://build/update-story.zip
```

Required environment variables for the function:

- `STORY_TABLE_NAME` – DynamoDB table that stores stories using a composite key `{ acctSiteID (PK), id (SK) }`.

After uploading the code, wire the resolver directly to the Lambda data source (no VTL templates needed):

```bash
aws appsync create-resolver \
  --api-id <API_ID> \
  --type-name Mutation \
  --field-name updateStory \
  --data-source-name <UpdateStoryLambdaDataSource>
```

Example CLI (replace placeholders):
```bash
aws appsync create-resolver \
  --api-id <API_ID> \
  --type-name Mutation \
  --field-name addAgents \
  --data-source-name <LAMBDA_DS_NAME> \
  --request-mapping-template file://graphql/resolvers/Mutation.addAgents.request.vtl \
  --response-mapping-template file://graphql/resolvers/Mutation.addAgents.response.vtl
```
Use `create-resolver` or `update-resolver` per field.

## 4) Environment variables for Lambda
Ensure these are set on the function:
- `DBAuroraClusterArn`
- `DBSecretsStoreArn`
- `DatabaseName`
- `AWS_REGION` (defaults to us-east-1 if unset)

## 5) Smoke tests
- Add agent:
  ```graphql
  mutation {
    addAgents(input:[{name:"A1", description:"demo"}]) { id success error }
  }
  ```
- List agents:
  ```graphql
  query { getAgents { id name owner status } }
  ```
- Query by name:
  ```graphql
  query { queryAgents(input:{name:"A1"}) { id name description } }
  ```

If invoking Lambda directly (bypassing AppSync):
```bash
aws lambda invoke --function-name <fn> --payload '{
  "arguments":{"input":[{"name":"A1"}]},
  "info":{"fieldName":"addAgents","parentTypeName":"Mutation"},
  "identity":{"claims":{"email":"owner@example.com"}}
}' out.json
cat out.json
```
