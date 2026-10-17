@pipeline @S12
Feature: S12 Librarian
  The librarian compares each candidate with ground truth. It labels it new, duplicate, conflict, stale or unverified.
  For a conflict, it proposes one change that fixes everything that depends on the old fact.

  @S12.01 @happy
  Scenario: A new fact is drafted for approval
    Actor: Librarian
    Given no fact exists about the onboarding fee
    When a candidate states the onboarding fee
    Then it is labelled "new"
    And a draft commit adds the fact with its evidence
    And a C3 change request opens for the DRI

  @S12.02 @happy
  Scenario: A duplicate only adds evidence
    Actor: Librarian
    Given the fact "refund window is 30 days" already exists
    When a candidate states the same value from another document
    Then it is labelled "duplicate"
    And the new evidence is linked to the existing fact
    And no change request opens

  @S12.03 @unhappy
  Scenario: A conflict bundles every dependent into one change
    Actor: Librarian
    Given the fact "refund window is 30 days" is on main
    When a candidate states "refund window is 14 days from 1 November"
    Then it is labelled "conflict"
    And the librarian lists every skill, policy, template and web page that depends on the old fact
    And one draft commit proposes the winning source, the new validity and every dependent update
    And a C3 change request opens

  @S12.04 @unhappy
  Scenario: A stale fact is proposed for closing
    Actor: Librarian
    Given a fact's valid time ended last month
    When the librarian reviews it
    Then it is labelled "stale"
    And a change request proposes closing its validity

  @S12.05 @unhappy
  Scenario: An unverified claim waits for a person
    Actor: Knowledge Steward (L2)
    Given a candidate is marked "unverified"
    When the knowledge steward opens the librarian queue
    Then the claim is listed with its evidence span
    And nothing is written to ground truth until it is verified

  @S12.06 @happy
  Scenario: A merged fact never overwrites the old one
    Actor: Version service
    Given the refund window conflict change request is approved
    When it merges
    Then the 14 day fact is written to main
    And the 30 day fact gets its valid time closed
    And both versions remain readable

  @S12.07 @unhappy
  Scenario: A conflict proposal is rejected
    Actor: Head of Customer Success (L1)
    Given the refund window conflict change request waits for the DRI
    When the DRI rejects it
    Then ground truth stays at 30 days
    And the conflict stays open in the librarian queue
