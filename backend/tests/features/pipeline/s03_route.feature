@pipeline @S3
Feature: S3 Route
  The resolver matches each Signal to an activity, a skill and an agent.
  It reads the resolver table from the production branch. When nothing fits, a person sees it.

  @S3.01 @happy
  Scenario: A refund email routes to the refund skill
    Actor: Resolver
    Given skill "refund_standard" version 4 is on main for the Refund Agent
    And a refund email Signal is on "signals.normalized"
    When the resolver scores it at 0.91
    Then one TaskRequest is published to "tasks.created"
    And it pins skill "refund_standard" version 4 with its commit ID
    And it carries a base criticality, a due time and a priority

  @S3.02 @happy
  Scenario: A close tie is broken by the fast model
    Actor: Resolver
    Given two resolver rules score within the tie margin for one Signal
    When the resolver asks Claude Haiku to break the tie
    Then one TaskRequest is published with the chosen rule ID
    And the trace records both scores and the tie break

  @S3.03 @happy
  Scenario: A task acts for a person
    Actor: Resolver
    Given the Signal is a request a human sent through the console
    When the resolver creates the task
    Then "on_behalf_of" names that human
    And the agent can never do more than that human may do

  @S3.04 @happy
  Scenario: A release changes routing for the next signal
    Actor: Resolver
    Given "graph.released" carries a new commit with skill "refund_late_annual" version 1
    When the resolver reloads its table
    Then the next matching Signal pins "refund_late_annual" version 1

  @S3.05 @unhappy
  Scenario: Nothing matches above the score floor
    Actor: Resolver
    Given the score floor is 0.72
    When the best rule scores 0.55 for a Signal
    Then the Signal goes to "tasks.unrouted"
    And the escalations queue shows it to a person
    And the nightly review counts it as a wrong route candidate

  @S3.06 @happy
  Scenario: A readiness gap dispatches an agent
    Actor: Resolver
    Given a GapDetected event with action "dispatch_agent" is on "evidence.gaps"
    When the resolver reads it
    Then a TaskRequest is published for the Compliance Agent to fetch the missing item

  @S3.07 @unhappy
  Scenario: The resolver missed a release
    Actor: Resolver
    Given the resolver did not receive the last release event
    When the next Signal arrives
    Then the commit check sees that main moved
    And the resolver reloads before it routes
