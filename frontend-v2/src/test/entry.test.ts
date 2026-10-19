import { expect, it } from "vitest";
import { loginDestination, legacyDestination } from "@/lib/entry";
it("session expiry returns to the exact V2 page and section", () => {
  const url = loginDestination({
    pathname: "/static/v2/index.html",
    search: "?date=10.19",
    hash: "#uploads",
  });
  expect(new URLSearchParams(url.split("?")[1]).get("next")).toBe(
    "/static/v2/index.html?date=10.19#uploads",
  );
});
it("legacy link stays on the old static page even after root switches", () => {
  expect(legacyDestination).toBe("/static/index.html");
});
