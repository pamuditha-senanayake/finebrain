@console @AP
Feature: L1 Approvals
  Approval weight follows criticality. Routine work flows by itself.
  Consequential work stops for the right person, and nothing passes by silence.

  @AP.01 @happy
  Scenario: The inbox is sorted by criticality and deadline
    Actor: Head of Customer Success (L1)
    When I open my approvals
    Then the highest criticality and nearest deadline come first

  @AP.02 @happy
  Scenario: Approve a new skill and it goes live
    Actor: Head of Customer Success (L1)
    Given the late refund skill passed tests and replay
    When I open it
    Then I see the plain diff, the replay, the tests and why it needs me
    When I approve
    Then it merges to Production
    And the Refund Agent uses it from now on

  @AP.03 @unhappy
  Scenario: Reject a change
    Actor: Head of Customer Success (L1)
    When I reject a change request with a comment
    Then the change request shows "rejected"
    And main does not change

  @AP.04 @unhappy
  Scenario: Ask for changes
    Actor: Head of Customer Success (L1)
    When I request changes with a comment
    Then the change request shows "changes requested"
    And the drafter can run the checks again after editing

  @AP.05 @happy
  Scenario: Delegate to another L1
    Actor: Head of Customer Success (L1)
    When I delegate an approval to the founder
    Then the founder gets a notification
    And the audit trail records the delegation

  @AP.06 @unhappy
  Scenario: Delegate to someone not allowed
    Actor: Head of Customer Success (L1)
    When I try to delegate a C3 approval to the care operator
    Then I read "Delegate must be L1"

  @AP.07 @happy
  Scenario: Two person rule for a critical change
    Actor: Founder (L1)
    Given a C4 capability grant proposed by the Security Sentinel
    When the head of customer success approves first
    Then it still needs a second, different L1 approver
    When I approve as the founder
    Then the grant merges and the Care Agent may refund up to LKR 10,000

  @AP.08 @unhappy
  Scenario: Approve a critical change twice as the same person
    Actor: Head of Customer Success (L1)
    Given I already approved a C4 request
    When I approve it again
    Then it is refused and still waits for another L1

  @AP.09 @unhappy
  Scenario: Approve my own draft
    Actor: Founder (L1)
    Given I drafted a change
    When I try to approve it
    Then I read "You drafted this change. Someone else must approve it."

  @AP.10 @unhappy
  Scenario: Approve above my ceiling
    Actor: AI Operations Lead (L2)
    When I try to approve a C3 change request
    Then it is refused because L2 approves up to C2

  @AP.11 @unhappy
  Scenario: Approve before tests and replay
    Actor: Head of Customer Success (L1)
    Given a change request has no test results
    When I try to approve it
    Then I read "Nothing goes live blind: run sandbox tests and the replay first."

  @AP.12 @unhappy
  Scenario: Approve after it expired
    Actor: Head of Customer Success (L1)
    Given an approval passed its deadline
    When I try to approve it
    Then I read "This approval expired. Ask the drafter to resubmit."

  @AP.13 @unhappy
  Scenario: Decide on something already decided
    Actor: Founder (L1)
    Given an approval was rejected
    When I try to approve it
    Then I read that it is already rejected

  @AP.14 @happy
  Scenario: Approve from a phone
    Actor: Head of Customer Success (L1)
    Given I open my approvals on a phone
    Then I can read the summary and approve without scrolling sideways
