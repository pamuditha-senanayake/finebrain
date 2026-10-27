import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // The Research Console is removable: product code must never import from it.
  {
    files: ["**/*.{ts,tsx}"],
    ignores: ["features/research/**", "app/(research)/**", "tests/unit/research-*.test.ts"], // research's own tests are not product code
    rules: {
      "no-restricted-imports": [
        "error",
        { patterns: [{ group: ["@/features/research", "@/features/research/*", "**/features/research/*"], message: "Product code must not import the Research Console. It reads the shared data layer, never the other way round." }] },
      ],
    },
  },
  globalIgnores([".next/**", ".next-*/**", "out/**", "build/**", "next-env.d.ts", "public/mockServiceWorker.js", "playwright-report/**", "test-results/**"]),
]);

export default eslintConfig;
