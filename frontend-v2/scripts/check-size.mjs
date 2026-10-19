import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";

const root = fileURLToPath(new URL("../../static/v2", import.meta.url));
function files(dir) {
  return readdirSync(dir)
    .sort()
    .flatMap((name) => {
      const item = resolve(dir, name);
      return statSync(item).isDirectory() ? files(item) : [item];
    });
}
const rows = files(root).map((file) => {
  const data = readFileSync(file);
  return {
    file: file.slice(root.length + 1).replaceAll("\\", "/"),
    bytes: data.length,
    gzipBytes: gzipSync(data).length,
  };
});
const javascript = rows
  .filter((row) => row.file.endsWith(".js"))
  .reduce((sum, row) => sum + row.gzipBytes, 0);
console.log(
  JSON.stringify(
    {
      files: rows,
      totalBytes: rows.reduce((sum, row) => sum + row.bytes, 0),
      allJavascriptGzipBytes: javascript,
      initialJavascriptLimitBytes: 300 * 1024,
    },
    null,
    2,
  ),
);
// All chunks combined is a stricter budget than the requested initial-entry budget.
if (javascript >= 300 * 1024) process.exitCode = 1;

const fixtureConfig = JSON.parse(
  readFileSync(new URL("../src/test/config.json", import.meta.url), "utf8"),
);
for (const file of files(root).filter((file) => file.endsWith(".js"))) {
  if (readFileSync(file, "utf8").includes(fixtureConfig.testOnlyHost))
    throw new Error("Test-only hostname leaked into production output");
}
