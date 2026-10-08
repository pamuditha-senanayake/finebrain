import type { Agent, GraphEdge, GraphNode, Human, Sensitivity } from "@/contracts";

export const SENSITIVITY_RANK: Record<Sensitivity, number> = { public: 0, internal: 1, confidential: 2, restricted: 3 };

export type Principal = {
  kind: "agent" | "human";
  id: string;
  name: string;
  capabilities: string[];
  roles: string[];
  level: Sensitivity;
};

export function agentPrincipal(agent: Agent): Principal {
  return { kind: "agent", id: agent.id, name: agent.name, capabilities: agent.capabilities, roles: [], level: agent.accessLevel };
}

export function humanPrincipal(human: Human): Principal {
  const level = (human.attributes.clearance as Sensitivity | undefined) ?? "internal";
  return { kind: "human", id: human.id, name: human.name, capabilities: human.roles.map((r) => `role:${r}`), roles: human.roles, level };
}

/** An agent acting for a human can never do more than that human may do. */
export function onBehalfOf(agent: Principal, human: Principal): Principal {
  const level = SENSITIVITY_RANK[agent.level] <= SENSITIVITY_RANK[human.level] ? agent.level : human.level;
  return {
    kind: "agent",
    id: agent.id,
    name: `${agent.name} for ${human.name}`,
    capabilities: agent.capabilities.filter((c) => human.roles.length === 0 || !c.startsWith("role:")),
    roles: human.roles,
    level,
  };
}

export type AccessCheck = { allowed: boolean; reason: string; ruleId: string };

export function checkNode(principal: Principal, node: Pick<GraphNode, "sensitivity" | "requires" | "label">): AccessCheck {
  // Tools are gated by capability first: that is the rule an agent can be granted.
  if (node.requires.capability && principal.kind === "agent" && !principal.capabilities.includes(node.requires.capability)) {
    return {
      allowed: false,
      ruleId: "capability-grant",
      reason: `requires capability ${node.requires.capability}, which ${principal.name} does not hold`,
    };
  }
  if (SENSITIVITY_RANK[node.sensitivity] > SENSITIVITY_RANK[principal.level]) {
    return {
      allowed: false,
      ruleId: "sensitivity-level",
      reason: `requires ${node.sensitivity} level, ${principal.name} holds ${principal.level} level`,
    };
  }
  if (node.requires.roles.length > 0 && principal.kind === "human" && !node.requires.roles.some((r) => principal.roles.includes(r))) {
    return {
      allowed: false,
      ruleId: "role-required",
      reason: `requires role ${node.requires.roles.join(" or ")}`,
    };
  }
  return { allowed: true, ruleId: "default-allow", reason: "allowed" };
}

export function checkEdge(principal: Principal, edge: GraphEdge, target: GraphNode): AccessCheck {
  const nodeCheck = checkNode(principal, target);
  if (!nodeCheck.allowed) return nodeCheck;
  if (edge.requiresCapability && principal.kind === "agent" && !principal.capabilities.includes(edge.requiresCapability)) {
    return {
      allowed: false,
      ruleId: "capability-grant",
      reason: `edge requires capability ${edge.requiresCapability}`,
    };
  }
  return nodeCheck;
}

/** Masks personal data by default. Reveal is a separate, audited call. */
export function maskPersonal(value: string): string {
  if (value.includes("@")) {
    const [user, domain] = value.split("@");
    return `${user.slice(0, 1)}•••@${domain}`;
  }
  if (value.length <= 4) return "••••";
  return `${value.slice(0, 2)}${"•".repeat(Math.max(3, value.length - 4))}${value.slice(-2)}`;
}
