@pipeline @S6
Feature: S6 Reason
  Claude plans the work and drafts a reply or an action. It cites every item it relies on.
  The action it proposes says exactly what it touches.

  @S6.01 @happy
  Scenario: The agent drafts a cited reply
    Actor: Agent runtime
    Given the Care Agent has a context bundle about invoice export
    When it judges the customer question
    Then it proposes action "reply_customer" with the drafted text
    And the proposal cites at least one item from the bundle

  @S6.02 @happy
  Scenario: A refund proposal says what it touches
    Actor: Agent runtime
    Given the Refund Agent decides a refund is fair
    When it proposes the action
    Then the action is "issue_refund" with payment ref, amount and reason code
    And the amount is stored in minor units with currency "LKR"
    And "touches" marks money as true

  @S6.03 @happy
  Scenario: The agent has no allowed facts to answer from
    Actor: Agent runtime
    Given the context bundle holds nothing about the question
    When the agent judges it
    Then it proposes action "escalate" with reason "missing_knowledge"
    And it does not guess an answer

  @S6.04 @unhappy
  Scenario: Invalid tool arguments are fixed on retry
    Actor: Agent runtime
    Given the first proposal has an amount written as a decimal number
    When the schema check fails
    Then the agent retries with the schema feedback
    And the second proposal passes the check

  @S6.05 @unhappy
  Scenario: Tool arguments stay invalid after two retries
    Actor: Agent runtime
    Given every proposal fails the schema check
    When the second retry also fails
    Then the run escalates with reason "invalid_tool_arguments"

  @S6.06 @unhappy
  Scenario: The model API fails
    Actor: Agent runtime
    Given the model API returns an error
    When the agent retries twice and both fail
    Then the run escalates with reason "model_unavailable"
