import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import inventory from "../../../docs/v2/inventory.json";
describe("inventory function excerpts use the actual source node", () => {
  for (const file of [
    ...new Set(inventory.groups.functions.map((row) => row.source)),
  ])
    it(file, () => {
      const source = ts.createSourceFile(
          file,
          readFileSync(resolve(process.cwd(), "..", file), "utf8"),
          ts.ScriptTarget.Latest,
          true,
          ts.ScriptKind.JS,
        ),
        nodes: ts.Node[] = [];
      const visit = (node: ts.Node) => {
        if (ts.isFunctionLike(node) && "body" in node && node.body)
          nodes.push(node);
        ts.forEachChild(node, visit);
      };
      visit(source);
      const rows = inventory.groups.functions.filter(
        (row) => row.source === file,
      );
      expect(nodes).toHaveLength(rows.length);
      rows.forEach((row, index) => {
        const node = nodes[index],
          start = source.getLineAndCharacterOfPosition(node.getStart(source));
        expect(row.line, row.id).toBe(start.line + 1);
        expect(row.detail, row.id).toBe(
          node.getText(source).replace(/\s+/g, " ").slice(0, 430),
        );
        expect(row.excerptStartLine, row.id).toBe(start.line + 1);
        expect(row.excerptStartColumn, row.id).toBe(start.character + 1);
      });
    });
});
