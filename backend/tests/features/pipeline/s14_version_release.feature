@pipeline @S14
Feature: S14 Version and release
  The graph works like git. Main is Production, and main only moves by a merge.
  Every merge is announced so the rest of the pipeline reloads.

  @S14.01 @happy
  Scenario: A merge releases a new version
    Actor: Version service
    Given an approved change request adds skill "refund_late_annual" version 1
    When it merges
    Then main points to a new commit with two parents and a release tag
    And "graph.released" carries the commit with the skill in its changed nodes
    And caches are cleared, the resolver reloads and the changed nodes are embedded again

  @S14.02 @unhappy
  Scenario: Two branches changed the same node
    Actor: Version service
    Given another change to the refund policy merged after this branch was made
    When this change request tries to merge
    Then it is marked "conflict"
    And the conflict view shows both sides with their evidence

  @S14.03 @unhappy
  Scenario: A C4 change merges before its cooling period ends
    Actor: Version service
    Given a C4 change is approved with a 24 hour cooling period
    When a merge is tried after 2 hours
    Then it is refused with "Cooling period has not ended"

  @S14.04 @unhappy
  Scenario: An approval comes before tests and replay
    Actor: Head of Customer Success (L1)
    Given a change request has no tests and no impact preview
    When the DRI tries to approve it
    Then it is refused with "Nothing goes live blind: run sandbox tests and the replay first."

  @S14.05 @happy
  Scenario: A rollback shows what reverts and then reverts it
    Actor: AI Operations Lead (L2)
    Given main has three commits after commit "M1"
    When the lead chooses roll back to "M1"
    Then the preview lists the three commits that will revert
    When the lead confirms
    Then a new rollback commit lands on main
    And skills added after "M1" are deprecated and removed from the resolver

  @S14.06 @unhappy
  Scenario: An L3 operator tries to roll back
    Actor: Customer Care Operator (L3)
    When the operator tries to roll back main
    Then it is refused with "Rollback needs L2 or L1"

  @S14.07 @unhappy
  Scenario: A direct edit to main is refused
    Actor: AI Operations Lead (L2)
    When anyone tries to change a node on main without a change request
    Then the edit is refused
    And it is saved as a draft on a sandbox branch instead
