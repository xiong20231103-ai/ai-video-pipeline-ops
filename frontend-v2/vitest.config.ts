import fixtureConfig from "./src/test/config.json" with { type: "json" };
import { defineConfig, mergeConfig } from "vitest/config";
import vite from "./vite.config.ts";

export default mergeConfig(
  vite,
  defineConfig({
    test: {
      environment: "jsdom",
      environmentOptions: { jsdom: { url: fixtureConfig.homeOrigin } },
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
    },
  }),
);
