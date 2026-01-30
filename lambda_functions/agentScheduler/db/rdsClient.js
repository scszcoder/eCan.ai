// Lightweight RDS Data API wrapper for MySQL/Aurora
// Uses named parameters and returns the raw ExecuteStatementCommand response
const { RDSDataClient, ExecuteStatementCommand } = require("@aws-sdk/client-rds-data");

const REGION = process.env.AWS_REGION || "us-east-1";
const resourceArn = process.env.DBAuroraClusterArn;
const secretArn = process.env.DBSecretsStoreArn;
const database = process.env.DatabaseName;

if (!resourceArn || !secretArn || !database) {
  // Fail fast so misconfiguration is obvious
  throw new Error("RDS config missing: ensure DBAuroraClusterArn, DBSecretsStoreArn, and DatabaseName env vars are set");
}

const client = new RDSDataClient({ region: REGION });

async function execute(sql, parameters = []) {
  const command = new ExecuteStatementCommand({
    resourceArn,
    secretArn,
    database,
    sql,
    parameters,
    includeResultMetadata: true
  });
  return client.send(command);
}

module.exports = {
  execute
};
