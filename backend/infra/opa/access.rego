# access.rego: who may do what to which data (K6). Asked by S7 (and later S5) at the moment of action.
# Input: principal {capabilities, tier}, action (a capability), resource {sensitivity}, on_behalf_of, on_behalf_of_tier.
# The same rules run in Python for memory runs: backend/app/pipeline/access.py (evaluate). Keep both in step.
package finebrain.access

readable := {
	"L1": {"public", "internal", "confidential", "restricted"},
	"L2": {"public", "internal", "confidential", "restricted"},
	"L3": {"public", "internal", "confidential"},
}

open_capabilities := {"escalate"}

has_capability if input.action in open_capabilities

has_capability if input.action in input.principal.capabilities

agent_may_read if input.resource.sensitivity in readable[input.principal.tier]

person_may_read if input.on_behalf_of == null

person_may_read if input.resource.sensitivity in readable[input.on_behalf_of_tier]

# First failing check wins, so every deny names its reason
decision := {"allow": false, "rule_id": "missing_capability", "reason": "principal lacks this capability"} if {
	not has_capability
} else := {"allow": false, "rule_id": "sensitivity_by_tier", "reason": "data too sensitive for this tier"} if {
	not agent_may_read
} else := {"allow": false, "rule_id": "on_behalf_of", "reason": "the person acted for may not see this data"} if {
	not person_may_read
} else := {"allow": true, "rule_id": "capability_and_tier", "reason": "capability held and data readable"}
