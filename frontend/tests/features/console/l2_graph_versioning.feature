@console @GV
Feature: L2 Graph and versioning
  The graph holds skills, policies, security, sensors, templates, facts, agents and tools.
  It works like git. Nothing goes live blind, and any commit can be reverted.

  @GV.01 @happy
  Scenario: Explore the graph
    Actor: AI Operations Lead (L2)
    When I open the graph
    And I switch between 3D, 2D and list views
    And I toggle node layers
    Then only the chosen node types show

  @GV.02 @happy
  Scenario: Test a draft skill before it goes live
    Actor: AI Operations Lead (L2)
    Given I open "New skill: Late refund with DRI approval" in versions
    When I run the sandbox tests and the replay
    Then the replay shows 37 of the last 412 refund conversations would change
    And it is C3 and waits for the L1 DRI

  @GV.03 @unhappy
  Scenario: Run the checks again after approval was requested
    Actor: AI Operations Lead (L2)
    Given the checks already ran and the request waits for approval
    When I run the checks again
    Then I read that the checks already ran

  @GV.04 @happy
  Scenario: Low criticality merges by itself after checks
    Actor: AI Operations Lead (L2)
    Given a C1 FAQ wording change is in draft
    When I run the checks and they pass
    Then it merges to main automatically and is logged

  @GV.05 @happy
  Scenario: Roll back safely
    Actor: AI Operations Lead (L2)
    When I choose roll back on an older commit on main
    Then I see every commit that would revert first
    When I confirm
    Then a rollback commit lands on main

  @GV.06 @unhappy
  Scenario: A rollback by L3
    Actor: Customer Care Operator (L3)
    When I try to roll back a commit
    Then I read "Rollback needs L2 or L1"

  @GV.07 @unhappy
  Scenario: A change request conflicts with a newer merge
    Actor: AI Operations Lead (L2)
    Given another change to the same node merged after this branch was made
    When this change request is approved
    Then it shows "conflict"
    And the resolution view shows both sides with their evidence

  @GV.08 @happy
  Scenario: Read a node's history and tags
    Actor: AI Operations Lead (L2)
    When I open the refund window node history
    Then I see every version with its commit, author and release tag
