import { z } from "zod";

export const IsoDate = z.string().describe("ISO 8601 timestamp, UTC");
export type IsoDate = z.infer<typeof IsoDate>;

export const Criticality = z.union([z.literal(0), z.literal(1), z.literal(2), z.literal(3), z.literal(4)]);
export type Criticality = z.infer<typeof Criticality>;

export const Env = z.enum(["production", "staging", "sandbox"]);
export type Env = z.infer<typeof Env>;

export const Tier = z.enum(["L1", "L2", "L3"]);
export type Tier = z.infer<typeof Tier>;

export const Sensitivity = z.enum(["public", "internal", "confidential", "restricted"]);
export type Sensitivity = z.infer<typeof Sensitivity>;

export const VersionRef = z.object({
  id: z.string(),
  version: z.number().int(),
  branch: z.string(),
});
export type VersionRef = z.infer<typeof VersionRef>;

export const Actor = z.object({
  kind: z.enum(["human", "agent", "system"]),
  id: z.string(),
  name: z.string(),
});
export type Actor = z.infer<typeof Actor>;

export const Money = z.object({
  amountMinor: z.number().int(),
  currency: z.string(),
});
export type Money = z.infer<typeof Money>;

export const NodeType = z.enum(["skill", "policy", "security", "sensor", "template", "fact", "document", "agent", "tool"]);
export type NodeType = z.infer<typeof NodeType>;

export const Touches = z.object({
  money: z.boolean(),
  personalData: z.boolean(),
  publicContent: z.boolean(),
  legalTax: z.boolean(),
  clusters: z.array(z.string()),
});
export type Touches = z.infer<typeof Touches>;
