@pipeline @S15
Feature: S15 Readiness
  Each hour the brain compares the evidence it needs with what it has. It notices gaps early.
  Then it fetches what is missing or asks the right person. People still file.

  @S15.01 @happy
  Scenario: The hourly tick finds a gap
    Actor: Readiness scheduler
    Given the September VAT return needs input invoices that do not exist yet
    When the hourly readiness tick runs
    Then a GapDetected event with its due date is published to "evidence.gaps"

  @S15.02 @happy
  Scenario: A gap far from its deadline dispatches an agent
    Actor: Readiness scheduler
    Given a gap is more than 21 days before its deadline
    When the action is chosen
    Then the action is "dispatch_agent"
    And no person is asked yet

  @S15.03 @happy
  Scenario: A gap close to its deadline asks the DRI
    Actor: Readiness scheduler
    Given a gap is within 21 days of its deadline
    When the action is chosen
    Then the action is "request_dri"
    And the finance director receives an evidence request

  @S15.04 @happy
  Scenario: A gap that needs a new source asks for a grant
    Actor: Readiness scheduler
    Given the input invoices live only in the finance inbox
    When the action is chosen
    Then the action is "request_grant"
    And the request shows the source, scope, retention, agents and how to revoke

  @S15.05 @unhappy
  Scenario: A request is already open for the same gap
    Actor: Readiness scheduler
    Given an evidence request for the input invoices is still open
    When the tick runs again
    Then no second request is created

  @S15.06 @unhappy
  Scenario: Nobody answers an evidence request
    Actor: Approval service
    Given an evidence request is unanswered
    When the deadline comes within 21, 14, 7 and then 2 days
    Then the request escalates at each of those points

  @S15.07 @happy
  Scenario: All evidence arrives and readiness turns green
    Actor: Finance Director (L1)
    Given the VAT return lacks the invoices and the bank statement
    When the finance director uploads both
    Then each item becomes a fact with provenance
    And readiness turns green
    And the record says a human still files

  @S15.08 @unhappy
  Scenario: Only part of the evidence arrives
    Actor: Finance Director (L1)
    Given the VAT return lacks two items
    When only the bank statement is uploaded
    Then readiness stays amber
    And the invoices request stays open

  @S15.09 @happy
  Scenario: An approved grant lets the agent fetch the evidence
    Actor: Founder (L1)
    Given a finance inbox grant is C4 and waits for two L1 approvers
    When the second L1 approves it
    Then the Compliance Agent gains "finance:read"
    And the finance inbox sensor starts reading
    And the open evidence request is fulfilled from that source

  @S15.10 @unhappy
  Scenario: A grant is revoked
    Actor: Security Officer (L2)
    Given the finance inbox grant is active
    When it is revoked
    Then the Compliance Agent loses "finance:read"
    And the finance inbox sensor stops

  @S15.11 @unhappy @proposed
  Scenario: A grant reaches the end of its retention
    Actor: Readiness scheduler
    Given a grant has a 90 day retention
    When 90 days pass
    Then access ends by itself
    And the DRI is told
