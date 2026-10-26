// Studio's typed inputs write back exactly what the pipeline stores: steps as "kind: text [tool:id]", schedules as cron.
import { describe, expect, it } from "vitest";
import { cronOf, planOf } from "@/features/studio/schedule-picker";
import { parseStep, writeStep } from "@/features/studio/steps-editor";

describe("steps", () => {
  it("reads and writes a tool step, a plain step and an untagged line", () => {
    const line = "tool: Reply to the visitor. [tool:reply_customer]";
    expect(parseStep(line)).toEqual({ kind: "tool", text: "Reply to the visitor.", tool: "tool:reply_customer" });
    expect(writeStep(parseStep(line))).toBe(line);
    expect(writeStep(parseStep("judgment: Answer from the docs."))).toBe("judgment: Answer from the docs.");
    expect(parseStep("Check the order first")).toEqual({ kind: "judgment", text: "Check the order first", tool: "" });
  });
  it("drops a tool tag when the step is no longer a tool step", () => {
    expect(writeStep({ kind: "judgment", text: "Decide", tool: "tool:escalate" })).toBe("judgment: Decide");
  });
});

describe("schedules", () => {
  it.each(["0 9 * * *", "30 7 * * 1-5", "0 9 * * 1", "15 6 3 * *", "5 * * * *"])("keeps %s through the picker", (cron) => {
    expect(cronOf(planOf(cron))).toBe(cron);
  });
  it("keeps anything else as a custom cron", () => {
    expect(planOf("*/15 9-17 * * 1-5").mode).toBe("custom");
    expect(cronOf(planOf("*/15 9-17 * * 1-5"))).toBe("*/15 9-17 * * 1-5");
  });
});
