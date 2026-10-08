// Builds an isolated copy of the app with the Research Console flag off and serves it on port 3101.
// The copy keeps tsconfig, next-env.d.ts and build output separate from the main project.
import { execSync, spawn } from "node:child_process";
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dest = process.env.NORESEARCH_DIR ?? join(tmpdir(), "cb-noresearch");
const port = process.env.PORT ?? "3101";
const skip = new Set(["node_modules", ".next", "playwright-report", "test-results", "screenshots", ".git"]);

rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
cpSync(root, dest, { recursive: true, filter: (src) => !skip.has(relative(root, src).split("/")[0]) });
// Copy on write clone where the filesystem supports it (APFS, btrfs, XFS), plain copy elsewhere.
const cloneFlag = process.platform === "darwin" ? "-cR" : "-R --reflink=auto";
execSync(`cp ${cloneFlag} "${join(root, "node_modules")}" "${join(dest, "node_modules")}"`, { stdio: "inherit" });

const env = { ...process.env, NEXT_PUBLIC_FLAG_RESEARCH: "disabled", NEXT_PUBLIC_MOCK_STREAM: "off", NEXT_PUBLIC_MOCK_LATENCY_MS: "20" };
execSync("npx next build", { cwd: dest, env, stdio: "inherit" });
if (!existsSync(join(dest, ".next"))) throw new Error("build output missing");
const server = spawn("npx", ["next", "start", "-p", port], { cwd: dest, env, stdio: "inherit" });
process.on("SIGTERM", () => server.kill("SIGTERM"));
process.on("SIGINT", () => server.kill("SIGINT"));
