/**
 * Tool handler: run_code
 * Execute JavaScript code in a sandboxed environment (/tmp).
 * Only Node.js is available on the Lambda runtime.
 */
import { execFile } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

const SANDBOX_DIR = "/tmp/sandbox";
const EXECUTION_TIMEOUT_MS = 15000; // 15s max

function execCode(code, args) {
  mkdirSync(SANDBOX_DIR, { recursive: true });
  const filename = `run_${randomUUID().slice(0, 8)}.mjs`;
  const filepath = join(SANDBOX_DIR, filename);
  writeFileSync(filepath, code, "utf-8");
  const cliArgs = [filepath, ...(args || [])];

  return new Promise((resolve) => {
    execFile("node", cliArgs, { timeout: EXECUTION_TIMEOUT_MS, cwd: SANDBOX_DIR, maxBuffer: 1024 * 512 }, (err, stdout, stderr) => {
      const result = {
        language: "javascript",
        exit_code: err?.code ?? 0,
        stdout: stdout?.slice(0, 10000) || "",
        stderr: stderr?.slice(0, 5000) || "",
      };
      if (err && !err.code) {
        result.error = err.message;
        result.exit_code = 1;
      }
      resolve(result);
    });
  });
}

export async function run_code(toolInput) {
  const { code, arguments: args } = toolInput;
  if (!code) {
    throw new Error("code is required");
  }

  const result = await execCode(code, args);
  return result;
}
