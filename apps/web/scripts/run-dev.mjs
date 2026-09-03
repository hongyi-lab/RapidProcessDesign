import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const port = process.env.WEB_PORT ?? "3900";
if (!/^\d+$/.test(port)) {
  console.error(`WEB_PORT must be a non-negative integer, received: ${port}`);
  process.exit(2);
}

const nextCli = fileURLToPath(
  new URL("../node_modules/next/dist/bin/next", import.meta.url),
);
const child = spawn(process.execPath, [nextCli, "dev", "-p", port], {
  stdio: "inherit",
  env: process.env,
});

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
