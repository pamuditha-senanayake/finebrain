@pipeline @S8
Feature: S8 Decide
  When a person must decide, the workflow waits. Each request has one DRI, a deadline and an expiry.
  Nothing is ever approved by silence.

  @S8.01 @happy
  Scenario: An approval request is created and the run waits
    Actor: Approval service
    Given governance routed a C3 refund to "approval_required"
    When the approval service creates the request
    Then "approvals.requested" carries one request with a plain summary
    And it names exactly one DRI, a due time and an expiry
    And the workflow sleeps until a decision or the expiry

  @S8.02 @happy
  Scenario: The DRI approves and the action runs
    Actor: Head of Customer Success (L1)
    Given a C3 refund approval waits for the DRI
    When the DRI approves it
    Then "approvals.decided" carries decision "approve"
    And the workflow wakes and the action runs

  @S8.03 @unhappy
  Scenario: The DRI rejects
    Actor: Head of Customer Success (L1)
    Given a C3 refund approval waits for the DRI
    When the DRI rejects it with a comment
    Then the action never runs
    And the run closes with outcome "blocked"

  @S8.04 @unhappy
  Scenario: The DRI asks for changes
    Actor: Head of Customer Success (L1)
    Given a C3 refund approval waits for the DRI
    When the DRI requests changes with a comment
    Then the action does not run
    And the agent receives the comment and drafts again

  @S8.05 @happy
  Scenario: The DRI delegates to an eligible person
    Actor: Head of Customer Success (L1)
    Given a C3 approval waits for the DRI
    When the DRI delegates it to the founder
    Then the founder receives the request
    And the decision records who delegated to whom

  @S8.06 @unhappy
  Scenario: Delegating to someone below the required tier
    Actor: Head of Customer Success (L1)
    Given a C3 approval needs an L1 approver
    When the DRI tries to delegate it to an L3 operator
    Then the delegation is refused with "Delegate must be L1"

  @S8.07 @happy
  Scenario: A person takes over and edits the action
    Actor: Customer Care Operator (L3)
    Given a refund approval waits
    When the operator takes over and changes the amount to LKR 40,000
    Then the decision carries the edited final arguments
    And the tool runs with LKR 40,000

  @S8.08 @happy
  Scenario: Two different L1 approvers clear a C4 request
    Actor: Founder (L1)
    Given a C4 request needs two L1 approvers
    When the head of customer success approves first
    Then the request still waits for one more approver
    When the founder approves second
    Then the request is approved

  @S8.09 @unhappy
  Scenario: The same person approves a C4 request twice
    Actor: Head of Customer Success (L1)
    Given the head of customer success already approved a C4 request
    When the same person approves it again
    Then the second vote is refused
    And the request still needs a different L1 approver

  @S8.10 @unhappy
  Scenario: The drafter tries to approve their own change
    Actor: AI Operations Lead (L2)
    Given the AI operations lead drafted a change
    When they try to approve it
    Then it is refused with "You drafted this change. Someone else must approve it."

  @S8.11 @unhappy
  Scenario: An L2 steward tries to approve a C3 request
    Actor: Knowledge Steward (L2)
    Given a C3 request waits
    When the knowledge steward tries to approve it
    Then it is refused because L2 approves up to C2 only

  @S8.12 @unhappy
  Scenario: Nobody answers before the expiry
    Actor: Approval service
    Given a C3 request reaches its expiry with no decision
    When the timer fires
    Then the decision becomes "expired"
    And the request escalates to the DRI's delegate
    And the action never runs on its own

  @S8.13 @unhappy
  Scenario: A decision arrives after the expiry
    Actor: Head of Customer Success (L1)
    Given a request already expired
    When the DRI tries to approve it
    Then it is refused with "This approval expired. Ask the drafter to resubmit."

  @S8.14 @unhappy
  Scenario: A decision arrives for a request already decided
    Actor: Founder (L1)
    Given a request was already rejected
    When the founder tries to approve it
    Then it is refused with "This approval is rejected"
