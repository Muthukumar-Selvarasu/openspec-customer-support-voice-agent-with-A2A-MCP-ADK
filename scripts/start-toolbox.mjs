import { readFileSync, writeFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const quote = (value) => JSON.stringify(String(value));
const formatKey = (key) => (/^[A-Za-z0-9_.-]+$/.test(key) ? key : quote(key));

export function buildToolsCatalog(databaseUrl, catalogTemplate) {
  const parsed = new URL(databaseUrl);
  const host = parsed.hostname;
  const port = parsed.port || "5432";
  const database = decodeURIComponent(parsed.pathname.replace(/^\//, ""));
  const user = decodeURIComponent(parsed.username);
  const password = decodeURIComponent(parsed.password);

  const queryEntries = Array.from(parsed.searchParams.entries());
  const queryParamsBlock =
    queryEntries.length > 0
      ? `\n    queryParams:\n${queryEntries
          .map(([key, value]) => `      ${formatKey(key)}: ${quote(value)}`)
          .join("\n")}`
      : "";

  return catalogTemplate
    .replace(/^    host:.*$/m, `    host: ${quote(host)}`)
    .replace(/^    port:.*$/m, `    port: ${port}`)
    .replace(/^    database:.*$/m, `    database: ${quote(database)}`)
    .replace(/^    user:.*$/m, `    user: ${quote(user)}`)
    .replace(/^    password:.*$/m, `    password: ${quote(password)}${queryParamsBlock}`);
}

export function main() {
  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    console.error("DATABASE_URL is required");
    process.exit(1);
  }

  const catalogPath = fileURLToPath(new URL("../mcp_toolbox/tools.yaml", import.meta.url));
  const catalog = buildToolsCatalog(databaseUrl, readFileSync(catalogPath, "utf8"));

  writeFileSync("/tmp/tools.yaml", catalog);
  const listenPort = process.env.PORT || "5000";
  const child = spawn(
    "npx",
    [
      "--no-install",
      "@toolbox-sdk/server",
      "--config",
      "/tmp/tools.yaml",
      "--enable-api",
      "--address",
      "0.0.0.0",
      "--port",
      listenPort,
    ],
    { stdio: "inherit" },
  );
  child.on("exit", (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    process.exit(code ?? 1);
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
