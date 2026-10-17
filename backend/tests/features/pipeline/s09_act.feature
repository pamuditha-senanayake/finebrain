@pipeline @S9
Feature: S9 Act
  The tool adapter calls the outside system. Every call carries an idempotency key.
  So a retry can never refund twice.

  @S9.01 @happy
  Scenario: An approved refund is called once and recorded
    Actor: Tool adapter
    Given a refund of LKR 85,000 is approved
    When the tool adapter calls the payment gateway
    Then the call carries idempotency key "{tenant}:{run_id}:{step_id}"
    And "actions.executed" records status "succeeded" with the gateway refund ID
    And the response summary holds no personal data

  @S9.02 @unhappy
  Scenario: A retryable failure succeeds on a later attempt
    Actor: Tool adapter
    Given the gateway times out on the first two calls
    When the adapter retries with backoff
    Then the third call succeeds
    And all three calls carried the same idempotency key
    And the gateway holds exactly one refund

  @S9.03 @unhappy
  Scenario: Retries run out
    Actor: Tool adapter
    Given the gateway keeps timing out
    When the sixth attempt also fails
    Then the action is recorded as "failed"
    And the run closes with outcome "failed"
    And the DRI is notified

  @S9.04 @unhappy
  Scenario: A failure that cannot be retried
    Actor: Tool adapter
    Given the gateway answers "card account closed"
    When the adapter reads the error as not retryable
    Then the action is recorded as "failed" at once
    And the human is notified
    And the defined compensation step runs and is recorded as "compensated"

  @S9.05 @unhappy
  Scenario: The same action is sent twice
    Actor: Tool adapter
    Given the refund call already succeeded
    When the workflow replays the same step
    Then the gateway sees the same idempotency key
    And it still holds exactly one refund

  @S9.06 @unhappy
  Scenario: Sandbox runs never reach real tools
    Actor: Tool adapter
    Given a run on a sandbox branch proposes a refund
    When the adapter receives it
    Then no outside system is called
    And the result is recorded as a simulated call
