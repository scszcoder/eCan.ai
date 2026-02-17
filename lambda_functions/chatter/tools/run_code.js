/**
 * Tool handler: run_code
 * Execute code in a sandboxed environment (/tmp).
 */
import { execFile } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

const SANDBOX_DIR = "/tmp/sandbox";
const EXECUTION_TIMEOUT_MS = 15000; // 15s max

export async function run_code(toolInput) {
  const { language, code, arguments: args } = toolInput;
  if (!language || !code) {
    throw new Error("language and code are required");
  }

  const lang = language.toLowerCase();
  const supportedLangs = { python: "python3", javascript: "node", bash: "bash" };
  const runtime = supportedLangs[lang];
  if (!runtime) {
    throw new Error(`Unsupported language: ${language}. Supported: ${Object.keys(supportedLangs).join(", ")}`);
  }

  // Write code to temp file
  mkdirSync(SANDBOX_DIR, { recursive: true });
  const ext = { python: ".py", javascript: ".js", bash: ".sh" }[lang];
  const filename = `run_${randomUUID().slice(0, 8)}${ext}`;
  const filepath = join(SANDBOX_DIR, filename);
  writeFileSync(filepath, code, "utf-8");

  const cliArgs = [filepath, ...(args || [])];

  return new Promise((resolve) => {
    execFile(runtime, cliArgs, { timeout: EXECUTION_TIMEOUT_MS, cwd: SANDBOX_DIR, maxBuffer: 1024 * 512 }, (err, stdout, stderr) => {
      const result = {
        language: lang,
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
