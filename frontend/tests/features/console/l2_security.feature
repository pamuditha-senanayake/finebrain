@console @SE
Feature: L2 Security and access
  Security binds at the moment of action. Every allow and deny is logged with its rule.
  Personal data is masked by default, and every reveal is audited.

  @SE.01 @happy
  Scenario: Investigate a denied action
    Actor: Security Officer (L2)
    When I open Security and access
    Then the Care Agent's refund attempt shows deny by its rule
    And the log shows the principal, who it acted for, the rule and the latency

  @SE.02 @happy
  Scenario: See what an agent can reach
    Actor: Security Officer (L2)
    Given I am on the knowledge graph
    When I choose view as Care Agent
    Then locked nodes and edges show the exact reason

  @SE.03 @happy
  Scenario: See what an agent can reach for a person
    Actor: Security Officer (L2)
    When I choose view as Care Agent acting for the care operator
    Then only what both may reach stays unlocked

  @SE.04 @happy
  Scenario: Reveal personal data with clearance
    Actor: Security Officer (L2)
    Given I hold confidential clearance
    When I reveal a masked customer email
    Then I see the real value
    And the reveal is written to the audit trail

  @SE.05 @unhappy
  Scenario: Reveal personal data without clearance
    Actor: Customer Care Operator (L3)
    Given I hold internal clearance
    When I try to reveal a masked customer email
    Then I read "Revealing personal data needs confidential clearance"

  @SE.06 @happy
  Scenario: A proposed grant waits for two L1 approvers
    Actor: Security Officer (L2)
    When I open the Security Sentinel's proposed refund grant
    Then it shows C4 and waits for two L1 approvals
