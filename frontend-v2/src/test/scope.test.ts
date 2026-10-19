import { expect, it } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import type { Row } from "@/data/types";
const root = resolve(process.cwd(), ".."),
  inventory = JSON.parse(
    readFileSync(resolve(root, "docs/v2/inventory.json"), "utf8"),
  ),
  rows = Object.values(inventory.groups).flat() as Row[];
it("all 900 legacy entries have an implementation or the explicit user-approved V2-4 exception", () => {
  expect(rows).toHaveLength(900);
  expect(new Set(rows.map((r) => r.id)).size).toBe(900);
  const pending = rows.filter((r) => !r.implemented);
  expect(pending).toHaveLength(22);
  for (const row of pending) {
    expect(["cloud/login.js", "cloud/login.html"]).toContain(row.source);
    expect(row.planned).toBe("V2-4");
    expect(row.disposition).toBe("user-deferred-login-registration-2026-10-20");
  }
  expect(rows.filter((r) => r.implemented)).toHaveLength(878);
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
    implemented: 878,
    total: 900,
    deferred: 22,
    productionShadowPassed: false,
    defaultEntrySwitched: false,
  });
});
