/**
 * Tool handler: find_files
 * Find files matching a pattern under a directory.
 */
import { execFile } from "node:child_process";

const FIND_TIMEOUT_MS = 10000;

export async function find_files(toolInput) {
  const { path, name, type } = toolInput;
  if (!path) {
    throw new Error("path is required");
  }

  // Restrict to /tmp for security in Lambda
  if (!path.startsWith("/tmp")) {
    throw new Error("Search path must be under /tmp for security.");
  }

  const args = [path];
  if (type) args.push("-type", type);
  if (name) args.push("-name", name);
  args.push("-maxdepth", "5"); // safety limit

  return new Promise((resolve) => {
    execFile("find", args, { timeout: FIND_TIMEOUT_MS, maxBuffer: 1024 * 256 }, (err, stdout, stderr) => {
      if (err) {
        resolve({ files: [], count: 0, error: stderr || err.message });
        return;
      }
      const files = stdout.trim().split("\n").filter(Boolean).slice(0, 500);
      resolve({ files, count: files.length });
    });
  });
}
