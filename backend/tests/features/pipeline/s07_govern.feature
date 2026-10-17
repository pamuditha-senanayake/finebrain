@pipeline @S7
Feature: S7 Govern
  Every proposed action passes four checks before it can run.
  First the access check, then the policy rules, then the quality gates, then criticality.
  The result is one of four routes: execute, approval required, escalate or block.

  @S7.01 @happy
  Scenario: A routine cited reply is cleared to run
    Actor: Governance service
    Given the Care Agent proposes a cited reply with no money and no personal data
    When governance checks it
    Then access is allowed and every policy passes
    And every quality gate passes
    And criticality is C0 and the route is "execute"

  @S7.02 @unhappy
  Scenario: Access is denied at action time
    Actor: Access service
    Given the Care Agent does not hold capability "tool:issue_refund"
    When it proposes a refund
    Then OPA answers deny with the rule and a plain reason
    And the route is "block"
    And the decision is logged in "access.decisions"

  @S7.03 @unhappy
  Scenario: The access service is unreachable at action time
    Actor: Access service
    Given OPA does not answer
    When an action is checked
    Then the decision is deny with reason "access_service_unavailable"
    And the route is "block"

  @S7.04 @happy
  Scenario: A refund inside policy and under the threshold
    Actor: Governance service
    Given refund policy version 3 has a 30 day window and an auto threshold of LKR 50,000
    When the Refund Agent proposes a refund of LKR 8,000 for a plan bought 12 days ago
    Then every policy passes
    And criticality is C2 from the activity default
    And the route follows the agent autonomy for C2

  @S7.05 @unhappy
  Scenario: A refund outside the window with no skill for it escalates
    Actor: Governance service
    Given skill "refund_standard" version 4 has no step for late refunds
    When the Refund Agent proposes a refund of LKR 85,000 for a plan bought 41 days ago
    Then the policy result fails with reasons "outside_refund_window" and "above_auto_threshold"
    And criticality is C3
    And the route is "escalate"

  @S7.06 @unhappy
  Scenario: A refund outside the window with a skill for it asks the DRI
    Actor: Governance service
    Given skill "refund_late_annual" version 1 is live
    When the Refund Agent proposes the same LKR 85,000 refund
    Then criticality is C3
    And the route is "approval_required" with one L1 approver

  @S7.07 @unhappy
  Scenario: A quality gate fails once and then passes
    Actor: Governance service
    Given the drafted reply promises a refund before approval
    When the tone gate fails
    Then the draft goes back to the agent once with the gate feedback
    And the second draft passes every gate

  @S7.08 @unhappy
  Scenario: A quality gate fails twice
    Actor: Governance service
    Given both drafts fail the grounding gate
    When the second draft fails
    Then the route is "escalate"

  @S7.09 @unhappy
  Scenario: A reply would leak personal data
    Actor: Governance service
    Given the draft holds a raw customer phone number
    When the personal data gate runs
    Then the gate fails
    And no reply is sent

  @S7.10 @unhappy
  Scenario: A factual claim has no citation
    Actor: Governance service
    Given the draft states a price with no cited item
    When the citation gate runs
    Then the gate fails with detail "uncited claim"

  @S7.11 @happy
  Scenario: Touching personal data moves criticality up one level
    Actor: Governance service
    Given an action starts at C2
    When it touches personal data
    Then criticality is C3
    And the reason "touches personal data" is recorded

  @S7.12 @happy
  Scenario: Spanning two clusters moves criticality up one level
    Actor: Governance service
    Given an action starts at C1
    When it touches the Finebase Platform and the Finance and Compliance clusters
    Then criticality is C2

  @S7.13 @happy
  Scenario: A critical action needs two L1 approvers and a cooling period
    Actor: Governance service
    Given an action deletes ground truth
    When governance checks it
    Then criticality is C4
    And the route is "approval_required" with two L1 approvers
    And a cooling period in hours is set
