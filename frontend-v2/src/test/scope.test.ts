import { expect, it } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import type { Row } from "@/data/types";
const root = resolve(process.cwd(), ".."),
  inventory = JSON.parse(
    readFileSync(resolve(root, "docs/v2/inventory.json"), "utf8"),
  ),
  rows = Object.values(inventory.groups).flat() as Row[];
it("all 904 inventoried entries now have implementations and isolated evidence", () => {
  expect(rows).toHaveLength(904);
  expect(new Set(rows.map((r) => r.id)).size).toBe(904);
  expect(rows.filter((r) => !r.implemented)).toHaveLength(0);
  const login = rows.filter(
    (r) => r.source === "cloud/login.js" || r.source === "cloud/login.html",
  );
  expect(login).toHaveLength(22);
  for (const row of login) {
    expect(row.pr).toBe(39);
    expect(row.evidence).toContain("tests/test_v2_entry.py");
  }
});
it("checked entries retain PR and corresponding worktree evidence paths", () => {
  for (const row of rows.filter((r) => r.implemented)) {
    expect(Number(row.pr)).toBeGreaterThanOrEqual(30);
    expect(Array.isArray(row.evidence) && row.evidence.length > 0).toBe(true);
    for (const path of row.evidence as string[])
      expect(existsSync(resolve(root, path)), row.id + ": " + path).toBe(true);
  }
});
it("current scope explicitly excludes production shadow and default entry switch", () => {
  expect(inventory.scopeDecision).toMatchObject({
    implemented: 904,
    total: 904,
    deferred: 0,
    productionShadowPassed: false,
    defaultEntrySwitched: false,
  });
});
