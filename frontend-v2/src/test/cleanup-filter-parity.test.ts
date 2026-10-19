import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import {
  cleanupFiltered,
  cleanupSpecs,
  type CleanupKind,
} from "@/data/home-cleanup";
import type { Row } from "@/data/types";
const source = readFileSync(resolve(process.cwd(), "../static/app.js"), "utf8");
const ast = ts.createSourceFile(
  "app.js",
  source,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.JS,
);
const functions = new Map(
  ast.statements
    .filter(ts.isFunctionDeclaration)
    .map((node) => [node.name?.text, node.getText(ast)]),
);
const filterIds: Record<string, string> = {
  category: "Category",
  date: "Date",
  project: "Project",
  material: "Material",
  language: "Language",
  audioBatch: "Batch",
  state: "State",
  query: "Search",
};
describe("cleanup filters: exact old/new same synthetic data", () => {
  for (const kind of ["drafts", "audio", "production"] as CleanupKind[])
    for (const filters of [
      {},
      { query: "Alpha" },
      { date: "2026-10-19" },
      { project: "P" },
      { category: "formal" },
      { state: "protected" },
      { state: "deletable" },
      { query: "语言" },
      { audioBatch: "B" },
      { language: "DE" },
    ]) {
      // Only fields actually present in each old manager are meaningful.
      const keys =
        kind === "drafts"
          ? ["category", "date", "query"]
          : kind === "audio"
            ? [
                "date",
                "project",
                "material",
                "language",
                "audioBatch",
                "state",
                "query",
              ]
            : ["date", "project", "material", "category", "state", "query"];
      const selected = Object.fromEntries(
        Object.entries(filters).filter(([key]) => keys.includes(key)),
      ) as Record<string, string>;
      it(`${kind} ${JSON.stringify(selected)}`, () => {
        const id = cleanupSpecs[kind].id,
          rows: Row[] = [
            {
              [id]: "a",
              name: "Alpha",
              sourceLabel: "source",
              relativePath: "folder",
              date: "2026-10-19",
              updatedAt: "2026-10-19T12:00:00+08:00",
              project: "P",
              material: "M",
              language: "DE",
              audioBatch: "B",
              category: "formal",
            },
            {
              [id]: "b",
              name: "Beta",
              sourceLabel: "语言",
              date: "2026-10-18",
              updatedAt: "2026-10-18T12:00:00+08:00",
              project: "Q",
              material: "N",
              language: "FR",
              category: "lab",
              protected: true,
            },
          ];
        const prefix = kind === "drafts" ? "draft" : kind,
          dom = new JSDOM(
            "<body>" +
              keys
                .map((key) => `<input id="${prefix}${filterIds[key]}Filter">`)
                .join("") +
              "</body>",
            { runScripts: "outside-only" },
          );
        for (const [key, value] of Object.entries(selected))
          (
            dom.window.document.getElementById(
              prefix + filterIds[key] + "Filter",
            ) as HTMLInputElement
          ).value = value;
        const functionName =
          kind === "drafts"
            ? "filteredDrafts"
            : kind === "audio"
              ? "filteredAudioFiles"
              : "filteredProductionFiles";
        const stateKey =
          kind === "drafts"
            ? "drafts"
            : kind === "audio"
              ? "audioFiles"
              : "productionFiles";
        dom.window.eval(
          `const $=id=>document.getElementById(id);const state={${stateKey}:${JSON.stringify(rows)}};${functions.get("draftDateKey")};${functions.get(functionName)};globalThis.filteredResult=${functionName}();`,
        );
        const old = Reflect.get(dom.window, "filteredResult") as Row[];
        expect(
          cleanupFiltered(kind, rows, selected).map((row) => row[id]),
        ).toEqual(Array.from(old, (row) => row[id]));
        dom.window.close();
      });
    }
});
