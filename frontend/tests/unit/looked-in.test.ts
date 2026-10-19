// The quiet line under Ask's sources says where the brain searched (step 13b).
import { describe, expect, it } from "vitest";
import { lookedInLabel } from "@/lib/looked-in";

describe("lookedInLabel", () => {
  it("names the linked things, then the domains", () => {
    expect(lookedInLabel({ level: "entity", domains: [], entityCount: 2 })).toBe("Looked in: 2 linked things");
    expect(lookedInLabel({ level: "entity", domains: ["customer_care"], entityCount: 1 })).toBe("Looked in: 1 linked thing · Customer care");
  });

  it("names the domain, or says everything", () => {
    expect(lookedInLabel({ level: "domain", domains: ["finance"], entityCount: 0 })).toBe("Looked in: Finance");
    expect(lookedInLabel({ level: "tenant", domains: [], entityCount: 0 })).toBe("Looked in: everything");
  });
});
