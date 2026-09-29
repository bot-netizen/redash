#!/usr/bin/env node
/*
  How much has to arrive before SQLDesk draws anything, and a limit on it.

  Run by CI. A page that loads slowly does so a few kilobytes at a time, and
  nobody notices until it is a second and a half -- so the number is measured
  on every build and a build that pushes it past the budget fails, with the
  file that grew named.

  What is measured: the assets webpack itself says the `app` entrypoint
  needs, gzipped. Not the whole of `dist`, which includes every lazily
  loaded chunk -- those are the point of the splitting, and counting them
  would punish moving code out of the initial load.
*/
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const ROOT = path.resolve(__dirname, "..");
const BUDGET_FILE = path.join(__dirname, "bundle-budget.json");
const DIST = path.join(ROOT, "client", "dist");

function build() {
  // `--json` writes the stats to stdout and the files to dist, so this is one
  // build serving both purposes rather than two.
  const out = execFileSync("npx", ["webpack", "--json"], {
    cwd: ROOT,
    env: { ...process.env, NODE_ENV: "production" },
    maxBuffer: 256 * 1024 * 1024,
    encoding: "utf8",
  });
  return JSON.parse(out);
}

function gzippedSize(file) {
  // Level 9, which is what a server serving these is expected to do, and what
  // the budget was set from.
  return zlib.gzipSync(fs.readFileSync(file), { level: 9 }).length;
}

function main() {
  const budget = JSON.parse(fs.readFileSync(BUDGET_FILE, "utf8"));
  const limit = budget.initialLoadKB;

  const stats = build();
  if (stats.errorsCount) {
    console.error("The build failed, so there is nothing to measure.");
    process.exit(1);
  }

  const entry = stats.entrypoints && stats.entrypoints.app;
  if (!entry) {
    console.error("webpack reported no `app` entrypoint; has the build been renamed?");
    process.exit(1);
  }

  const files = entry.assets
    .map((asset) => asset.name)
    .filter((name) => /\.(js|css)$/.test(name))
    .map((name) => ({ name, kb: gzippedSize(path.join(DIST, name)) / 1024 }))
    .sort((a, b) => b.kb - a.kb);

  const total = files.reduce((sum, f) => sum + f.kb, 0);

  console.log("\nWhat loads before anything draws (gzipped):\n");
  for (const f of files) {
    console.log(`  ${f.kb.toFixed(0).padStart(5)} KB  ${f.name}`);
  }
  console.log(`  ${"-".repeat(5)}`);
  console.log(`  ${total.toFixed(0).padStart(5)} KB  total, against a budget of ${limit} KB\n`);

  if (total > limit) {
    console.error(
      `Over budget by ${(total - limit).toFixed(0)} KB.\n\n` +
        `Something now loads before it is needed. The usual cause is a module imported\n` +
        `at the top of a file that runs at startup -- pages/index.js imports every page's\n` +
        `routes, so anything reachable from one of those reaches everybody.\n\n` +
        `To see what moved:\n` +
        `  NODE_ENV=production npx webpack --json --stats-modules --stats-chunk-modules > stats.json\n` +
        `and compare the packages in the app entrypoint's chunks against the last build.\n\n` +
        `If the growth is genuinely worth it, raise the number in client/bundle-budget.json\n` +
        `in the same change, so the decision is reviewed rather than discovered later.`
    );
    process.exit(1);
  }

  const headroom = limit - total;
  console.log(`Within budget, ${headroom.toFixed(0)} KB to spare.`);
}

main();
