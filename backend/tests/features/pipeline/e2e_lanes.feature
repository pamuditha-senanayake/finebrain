@pipeline @E2E
Feature: End to end lanes
  These scenarios run the whole pipeline. Every check looks at the system from outside.
  That means the outside sandboxes, the public API, the SSE stream and the Kafka topics.

  Background:
    Given tenant "Finebase Labs" with currency LKR and timezone Asia/Colombo
    And the clock is frozen for the test

  @E2E.01 @happy
  Scenario: A routine chat question is answered in under 10 seconds
    Actor: Customer
    Given the Care Agent is autonomous for product questions
    When a customer asks on chat how to export invoices
    Then the chat receives one cited reply within 10 seconds
    And one run closes with outcome "resolved" and no human touch
    And one trace ID links the webhook, every step and the console event

  @E2E.02 @happy
  Scenario: A late refund becomes a governed skill
    Actor: Customer, operator and DRI
    Given policy "refund_policy" version 3 on main has a 30 day window and an auto threshold of LKR 50,000
    And skill "refund_standard" version 4 is live for the Refund Agent
    And customer "C1" bought an annual plan for LKR 85,000 41 days ago
    And the head of customer success is the L1 DRI for refunds
    When customer "C1" emails the support inbox asking for a full refund
    Then the thread gets one acknowledgement within 10 seconds with no refund promise
    And the escalations queue lists "C1" with reasons "outside_refund_window" and "above_auto_threshold"
    And the payment sandbox has received no refund call
    When the L3 operator takes over and proposes a full refund of LKR 85,000
    Then one C3 approval is assigned to the head of customer success
    When the head of customer success approves it
    Then the payment sandbox receives exactly one refund of LKR 85,000 with the run idempotency key
    And the customer gets one confirmation reply
    And the refund register has a new row whose source is the gateway refund ID
    When the operator presses Skillify on the closed conversation
    Then a sandbox branch holds draft skill "refund_late_annual" version 1
    And its change request shows passing tests and a replay of at least 50 refund runs
    And the change request is C3 and waits for the head of customer success
    When the head of customer success approves and merges it
    Then "graph.released" carries the new commit with the new skill
    When customer "C2" with the same plan and age emails for a refund
    Then the run for "C2" uses "refund_late_annual" version 1
    And an approval is created for the DRI without any escalation
    And the payment sandbox receives no refund call before that approval
    And the audit trail returns every step above in order with an unbroken hash chain
    And no message, response or event contains the raw name or email of "C1" or "C2"

  @E2E.03 @happy
  Scenario: A new pricing document updates ground truth
    Actor: Knowledge Steward and DRI
    Given the fact "refund window is 30 days" is on main
    When a pricing PDF stating a 14 day window from 1 November is uploaded
    Then the Library lists the document with its sensitivity and retention
    And the librarian queue shows a conflict with every dependent listed
    When the knowledge steward asks the librarian to propose a resolution
    And the checks run
    Then one C3 change request waits for the DRI
    When the DRI approves it
    Then Ask the Brain answers 14 days for dates from 1 November
    And it answers 30 days for dates before that

  @E2E.04 @happy
  Scenario: A tax deadline is made ready early
    Actor: Finance Director and Founder
    Given the September VAT return is due in 20 days and lacks input invoices
    When the readiness tick runs
    Then the finance director receives an evidence request with a suggested finance inbox grant
    When the finance director requests the grant
    And the founder and the head of customer success both approve it
    Then the Compliance Agent reads the invoices from the finance inbox
    And readiness for the VAT return turns green
    And no filing is made by the brain

  @E2E.05 @unhappy
  Scenario: A refund the agent may not make is blocked end to end
    Actor: Customer
    Given the Care Agent does not hold capability "tool:issue_refund"
    When a customer asks the Care Agent for a refund on chat
    Then the run is blocked at the access check
    And the Security decision log shows the deny with its rule
    And the payment sandbox receives no call
    And the customer is told a person will follow up

  @E2E.06 @unhappy
  Scenario: An approval nobody answers never runs by itself
    Actor: Approval service
    Given a C3 refund approval is created
    When its expiry passes with no decision
    Then the approval shows "expired"
    And the request moves to the DRI's delegate
    And the payment sandbox receives no call
