@pipeline @S5
Feature: S5 Retrieve
  The agent asks for context. The context service returns only what the agent may see.
  Every allowed and denied item is logged.

  @S5.01 @happy
  Scenario: Allowed facts come back with their source and valid time
    Actor: Context service
    Given the Refund Agent holds "internal" level
    When it asks "What is the refund window for annual plans?"
    Then the bundle holds the refund window fact with its document, page and span
    And each item shows valid from, valid to and recorded at
    And the answer comes back within 2 seconds

  @S5.02 @happy
  Scenario: An agent acting for a person gets the smaller set of rights
    Actor: Context service
    Given the Care Agent holds "confidential" level
    And it acts for an operator who holds "internal" level
    When it asks for context
    Then only items at "internal" level or below come back

  @S5.03 @happy
  Scenario: A question about the past reads facts as of that date
    Actor: Context service
    Given the refund window was 30 days until 31 October and 14 days after
    When the agent asks with "as_of_valid" set to 15 October
    Then the bundle holds the 30 day fact

  @S5.04 @happy
  Scenario: What the brain believed then can differ from what was true
    Actor: Context service
    Given the 14 day window was recorded on 20 October with valid from 1 October
    When the agent asks with "as_of_valid" 10 October and "as_of_recorded" 15 October
    Then the bundle holds the 30 day fact the brain believed on 15 October

  @S5.05 @happy
  Scenario: A replay reads from a sandbox branch
    Actor: Context service
    Given a sandbox branch changes the refund window
    When a replay asks for context on that branch
    Then the bundle holds the sandbox version of the fact

  @S5.06 @unhappy
  Scenario: Restricted items are counted but never returned
    Actor: Context service
    Given three matching chunks are "restricted" and the agent holds "internal"
    When it asks for context
    Then those chunks are not in the bundle
    And "denied_count" is 3 with the deciding rule
    And three deny records are written to "access.decisions"

  @S5.07 @unhappy
  Scenario: Retrieval times out once and then works
    Actor: Context service
    Given the first context query takes longer than 2 seconds
    When the agent retries once
    And the retry answers in time
    Then the run continues with the bundle

  @S5.08 @unhappy
  Scenario: Retrieval times out twice
    Actor: Context service
    Given both context queries take longer than 2 seconds
    When the retry also times out
    Then the run escalates with reason "context_unavailable"

  @S5.09 @unhappy
  Scenario: The access service is unreachable during retrieval
    Actor: Access service
    Given OPA does not answer
    When the context service checks an item
    Then the item is denied with reason "access_service_unavailable"
    And nothing unchecked is returned
