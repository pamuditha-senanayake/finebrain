@pipeline @S10
Feature: S10 Record
  The recorder closes every run. It fills templates, stores the trace and appends the audit.
  Then the live console updates for everyone allowed to see it.

  @S10.01 @happy
  Scenario: A template field is filled with its source
    Actor: Template service
    Given the refund succeeded with a gateway refund ID
    When the recorder fills the refund register
    Then a new row holds the value, the source item and a fresh until time

  @S10.02 @happy
  Scenario: A run closes with its full trace
    Actor: Recorder
    Given run "R1" finished all its steps
    When the recorder closes it
    Then the full trace is stored in object storage
    And one RunRecord with outcome, cost and latency is published to "runs.completed"

  @S10.03 @happy
  Scenario: Every consequential step is appended to the audit chain
    Actor: Audit service
    Given run "R1" executed a refund
    When the audit event is appended
    Then its "prev_hash" equals the hash of the event before it

  @S10.04 @happy
  Scenario: Live updates reach only allowed viewers with data masked
    Actor: SSE gateway
    Given an approval was created for a refund
    When the gateway pushes "approval.created"
    Then every viewer allowed to see it receives the event
    And the event shows masked personal data only

  @S10.05 @unhappy
  Scenario: A viewer without permission does not receive the event
    Actor: SSE gateway
    Given an L3 operator is not allowed to see finance approvals
    When a finance approval is created
    Then the operator's stream does not carry it

  @S10.06 @unhappy
  Scenario: The recorder is down for a while
    Actor: Recorder
    Given the recorder stops for 10 minutes
    When it starts again
    Then it catches up from Kafka with no lost runs
    And the console shows "delayed" while it catches up

  @S10.07 @unhappy @proposed
  Scenario: Someone edits an audit event
    Actor: Audit service
    Given an audit event was changed after it was written
    When the chain is verified
    Then verification fails at that event
    And the break is shown in the audit trail
