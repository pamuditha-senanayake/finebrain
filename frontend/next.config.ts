import type { NextConfig } from "next";

// The Research Console's route files end in `.research.tsx`. They only become routes when the flag
// is on, so with the flag off its pages, navigation and bundles do not exist in the build at all.
const researchEnabled = process.env.NEXT_PUBLIC_FLAG_RESEARCH === "enabled";

// Every screen reads its data in the browser through typed contracts (TanStack Query), so there is
// nothing for Cache Components to prerender. It stays off to keep URL hooks free of Suspense rules.
const nextConfig: NextConfig = {
  pageExtensions: [...(researchEnabled ? ["research.tsx"] : []), "tsx", "ts"],
  experimental: { agentUpgrade: "security" },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
