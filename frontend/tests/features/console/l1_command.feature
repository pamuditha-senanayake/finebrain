@console @L1
Feature: L1 Command
  L1 is for founders, directors and DRIs. They follow progress and risk.
  They also protect the legal entity and read the full audit.

  @L1.01 @happy
  Scenario: See the business at a glance
    Actor: Founder (L1)
    When I open the Brain overview
    Then each cluster shows health, autonomy, escalations, money at stake and cost
    And the legibility map shows which activities are not yet sensed, skilled, governed or reported

  @L1.02 @happy
  Scenario: Open a cluster for detail
    Actor: Founder (L1)
    When I click the Finebase Platform cluster on the brain map
    Then its parts and workflows open as grouped tables

  @L1.03 @happy
  Scenario: Read the morning digest
    Actor: Founder (L1)
    When I open To review
    Then I see what happened overnight
    And C0 and C1 fixes were applied and logged
    And bigger changes wait for a decision

  @L1.04 @happy
  Scenario: Protect the legal entity
    Actor: Finance Director (L1)
    When I open Entity protection
    Then each obligation shows readiness, missing evidence, a countdown and its DRI
    And every date is labelled as sample data
    And the risk register lists each risk with its owner

  @L1.05 @happy
  Scenario: Follow progress
    Actor: Founder (L1)
    When I open Progress
    Then I compare clusters, loops, experiments and template completion

  @L1.06 @happy
  Scenario: Follow one story in the audit trail
    Actor: Founder (L1)
    When I open the audit trail for the customer 1042 refund story
    Then I see takeover, Skillify, tests, approval and merge in order
    And each line names who did it

  @L1.07 @happy
  Scenario: Filter the audit trail
    Actor: Founder (L1)
    When I filter by actor, object, environment and criticality
    Then only matching events remain

  @L1.08 @unhappy
  Scenario: The audit trail cannot be edited
    Actor: Founder (L1)
    When I open any audit event
    Then there is no edit or delete control

  @L1.09 @happy
  Scenario: See the past with the as of view
    Actor: Founder (L1)
    When I move the as of date to last month
    Then the overview shows what was true then
