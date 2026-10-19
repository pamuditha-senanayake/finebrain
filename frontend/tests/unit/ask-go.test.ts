// "Go to the library" opens the page; other words stay a normal question.
import { describe, expect, it } from "vitest";
import type { Human } from "@/contracts";
import { findPage } from "@/lib/ask-go";

const person = (tier: Human["tier"]) => ({ id: "h", tier, roles: [] }) as unknown as Human;

describe("findPage", () => {
  it("finds a page by its name, with or without the, page, or please", () => {
    expect(findPage("go to the library", person("L1"))?.href).toBe("/l2/library");
    expect(findPage("Please open audit trail page", person("L1"))?.href).toBe("/l1/audit");
    expect(findPage("take me to trends.", person("L1"))?.href).toBe("/l1/trends");
  });

  it("knows a few short names", () => {
    expect(findPage("go to approvals", person("L1"))?.href).toBe("/l1/digest");
  });

  it("leaves questions alone, and only offers pages the person may open", () => {
    expect(findPage("show me the refund policy", person("L1"))).toBeNull();
    expect(findPage("open a refund for Nimal", person("L1"))).toBeNull();
    expect(findPage("go to library", person("L3"))).toBeNull();
    expect(findPage("go to library", null)).toBeNull();
  });
});
