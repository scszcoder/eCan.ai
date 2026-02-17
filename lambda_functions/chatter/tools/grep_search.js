/**
 * Tool handler: grep_search
 * Search for text patterns in files using grep.
 */
import { execFile } from "node:child_process";

const SEARCH_TIMEOUT_MS = 10000;

export async function grep_search(toolInput) {
  const { pattern, path, recursive } = toolInput;
  if (!pattern || !path) {
    throw new Error("pattern and path are required");
  }

  // Restrict to /tmp for security in Lambda
  if (!path.startsWith("/tmp")) {
    throw new Error("Search path must be under /tmp for security.");
  }

  const args = ["-n", "--color=never"];
  if (recursive) args.push("-r");
  args.push(pattern, path);

  return new Promise((resolve) => {
    execFile("grep", args, { timeout: SEARCH_TIMEOUT_MS, maxBuffer: 1024 * 256 }, (err, stdout, stderr) => {
      if (err && err.code === 1) {
        // grep exit code 1 = no matches
        resolve({ matches: [], count: 0 });
        return;
      }
      if (err && err.code !== 1) {
        resolve({ matches: [], count: 0, error: stderr || err.message });
        return;
      }
      const lines = stdout.trim().split("\n").filter(Boolean);
      const matches = lines.slice(0, 200).map(line => {
        const parts = line.split(":");
        return { file: parts[0], line_number: parseInt(parts[1], 10) || 0, text: parts.slice(2).join(":") };
      });
      resolve({ matches, count: matches.length });
    });
  });
}
