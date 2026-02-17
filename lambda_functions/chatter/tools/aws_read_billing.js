/**
 * Tool handler: aws_read_billing
 * Read AWS billing and cost data.
 */
import { CostExplorerClient, GetCostAndUsageCommand } from "@aws-sdk/client-cost-explorer";

const ce = new CostExplorerClient({ region: "us-east-1" });

export async function aws_read_billing(toolInput) {
  const { period } = toolInput;
  if (!period) {
    throw new Error("period is required");
  }

  const now = new Date();
  let startDate, endDate;

  if (period === "current_month") {
    startDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
    endDate = now.toISOString().slice(0, 10);
  } else if (period === "last_month") {
    const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const lastMonthEnd = new Date(now.getFullYear(), now.getMonth(), 0);
    startDate = lastMonth.toISOString().slice(0, 10);
    endDate = lastMonthEnd.toISOString().slice(0, 10);
  } else {
    // Expect ISO date range: "2026-01-01/2026-01-31"
    const parts = period.split("/");
    startDate = parts[0];
    endDate = parts[1] || now.toISOString().slice(0, 10);
  }

  const resp = await ce.send(new GetCostAndUsageCommand({
    TimePeriod: { Start: startDate, End: endDate },
    Granularity: "MONTHLY",
    Metrics: ["UnblendedCost", "UsageQuantity"],
    GroupBy: [{ Type: "DIMENSION", Key: "SERVICE" }],
  }));

  const results = (resp.ResultsByTime || []).map(r => ({
    period: r.TimePeriod,
    groups: (r.Groups || []).map(g => ({
      service: g.Keys?.[0],
      cost: g.Metrics?.UnblendedCost?.Amount,
      unit: g.Metrics?.UnblendedCost?.Unit,
    })),
    total: r.Total?.UnblendedCost?.Amount,
  }));

  return { period, billing: results };
}
