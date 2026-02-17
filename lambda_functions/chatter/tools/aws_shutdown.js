/**
 * Tool handler: aws_shutdown
 * Emergency shutdown of AWS resources to control costs.
 *
 * Supports stopping EC2 instances, RDS clusters/instances, and ECS services.
 * If resource_id is omitted, lists running resources of that type instead of
 * shutting them all down (safety measure).
 */
import { EC2Client, StopInstancesCommand, DescribeInstancesCommand } from "@aws-sdk/client-ec2";
import { RDSClient, StopDBInstanceCommand, StopDBClusterCommand } from "@aws-sdk/client-rds";
import { ECSClient, UpdateServiceCommand, ListServicesCommand } from "@aws-sdk/client-ecs";

const ec2 = new EC2Client({ region: "us-east-1" });
const rds = new RDSClient({ region: "us-east-1" });
const ecs = new ECSClient({ region: "us-east-1" });

const ECS_CLUSTER = process.env.ECS_CLUSTER || "";

export async function aws_shutdown(toolInput) {
  const { resource_type, resource_id } = toolInput;
  if (!resource_type) {
    throw new Error("resource_type is required (ec2, rds, ecs)");
  }

  const type = resource_type.toLowerCase();

  switch (type) {
    case "ec2": {
      if (!resource_id) {
        // List running instances instead of blanket shutdown
        const desc = await ec2.send(new DescribeInstancesCommand({
          Filters: [{ Name: "instance-state-name", Values: ["running"] }],
        }));
        const instances = (desc.Reservations || []).flatMap(r =>
          (r.Instances || []).map(i => ({
            instance_id: i.InstanceId,
            type: i.InstanceType,
            name: (i.Tags || []).find(t => t.Key === "Name")?.Value || "",
            state: i.State?.Name,
          }))
        );
        return { action: "list", resource_type: "ec2", instances, count: instances.length, message: "Provide resource_id to stop a specific instance." };
      }
      await ec2.send(new StopInstancesCommand({ InstanceIds: [resource_id] }));
      return { action: "stop", resource_type: "ec2", resource_id, status: "stopping" };
    }

    case "rds": {
      if (!resource_id) {
        return { action: "list", resource_type: "rds", message: "Provide resource_id (DB instance or cluster identifier) to stop." };
      }
      try {
        await rds.send(new StopDBInstanceCommand({ DBInstanceIdentifier: resource_id }));
        return { action: "stop", resource_type: "rds", resource_id, status: "stopping" };
      } catch (err) {
        if (err.name === "InvalidDBInstanceState" || err.name === "DBInstanceNotFoundFault") {
          // Try as cluster
          await rds.send(new StopDBClusterCommand({ DBClusterIdentifier: resource_id }));
          return { action: "stop", resource_type: "rds_cluster", resource_id, status: "stopping" };
        }
        throw err;
      }
    }

    case "ecs": {
      const cluster = ECS_CLUSTER;
      if (!cluster) {
        throw new Error("ECS_CLUSTER env var not set");
      }
      if (!resource_id) {
        const listResp = await ecs.send(new ListServicesCommand({ cluster }));
        return { action: "list", resource_type: "ecs", cluster, services: listResp.serviceArns || [], message: "Provide resource_id (service name/ARN) to scale down." };
      }
      // Scale service to 0 desired tasks
      await ecs.send(new UpdateServiceCommand({
        cluster,
        service: resource_id,
        desiredCount: 0,
      }));
      return { action: "scale_to_zero", resource_type: "ecs", resource_id, status: "scaling_down" };
    }

    default:
      return { error: `Unsupported resource_type: ${resource_type}. Supported: ec2, rds, ecs` };
  }
}
