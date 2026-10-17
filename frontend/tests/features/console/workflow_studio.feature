@console @WS
Feature: Workflow Studio
  Workflow Studio is where people shape how the brain works. A chat sits beside the parts of each workflow.
  Every edit goes to the Edit Review Agent first. Then it applies at once or goes for approval.

  @WS.01 @happy
  Scenario: Read why a workflow exists
    Actor: Any user
    When I pick the refunds workflow
    Then I see the problem, how it is handled today and its cases as BDD stories
    And each case shows which parts cover it

  @WS.02 @happy
  Scenario: Describe a new problem in chat
    Actor: Founder (L1)
    When I describe a problem the brain does not handle yet
    Then the assistant drafts a story with its cases
    And I confirm the cases before anything is built

  @WS.03 @happy
  Scenario: Ask for a change in plain words
    Actor: Founder (L1)
    When I ask the assistant to raise the refund auto threshold to LKR 60,000
    Then it shows a proposal card with the before and after values
    And the Edit Review Agent gives a verdict, a criticality and what else is affected

  @WS.04 @unhappy
  Scenario: The assistant is not sure what I mean
    Actor: Any user
    When I ask for a change that could fit two parts
    Then the assistant asks which part I mean

  @WS.05 @unhappy
  Scenario: The change would change nothing
    Actor: Founder (L1)
    When I ask to set a value to what it already is
    Then I read "Nothing would change. Say what the new value should be."

  @WS.06 @happy
  Scenario: A low risk edit applies at once
    Actor: Head of Customer Success (L1)
    Given the Edit Review Agent marks a description edit minimal and C0
    When I confirm it
    Then it applies at once and is logged

  @WS.07 @happy
  Scenario: A C2 edit by the workflow owner applies at once
    Actor: Head of Customer Success (L1)
    Given I own the refunds workflow
    And the review marks my edit moderate and C2
    When I confirm it
    Then it applies at once because C2 is inside my ceiling

  @WS.08 @happy
  Scenario: A C3 edit goes for approval
    Actor: Founder (L1)
    Given the review marks my policy edit C3
    When I confirm it
    Then it opens a change request on a sandbox branch
    And the checks run and it waits for the DRI
    And it applies when it merges

  @WS.09 @happy
  Scenario: An L2 steward drafts and never applies
    Actor: AI Operations Lead (L2)
    When I confirm any edit
    Then it is sent for approval at C2 or above
    And it never applies by my hand

  @WS.10 @unhappy
  Scenario: An L3 operator tries to apply an edit
    Actor: Customer Care Operator (L3)
    When I try to confirm an edit
    Then I read "L3 can view workflows and suggest edits, but cannot change them."

  @WS.11 @happy
  Scenario: An L3 operator suggests an edit
    Actor: Customer Care Operator (L3)
    When I send an edit as a suggestion
    Then the workflow DRI is notified with the review verdict
    And nothing changes until the DRI acts

  @WS.12 @unhappy
  Scenario: A breaking edit sent without reading the review
    Actor: Founder (L1)
    Given the review marks my edit breaking
    When I send it without confirming the review
    Then I read "The Edit Review Agent marked this breaking. Read the review and confirm before sending it."

  @WS.13 @happy
  Scenario: A breaking edit sent after reading the review
    Actor: Founder (L1)
    Given the review marks my edit breaking
    When I confirm the review and send it
    Then it goes for approval at C2 or above with the problems noted

  @WS.14 @happy
  Scenario: Apply the suggested fixes first
    Actor: Founder (L1)
    Given the review lists a fix for a breaking problem
    When I apply the fix
    Then the review runs again without that problem

  @WS.15 @unhappy
  Scenario: Delete a part others depend on
    Actor: Founder (L1)
    When I ask to delete a tool that an active skill uses
    Then the review marks it breaking
    And it names the skill that would point at nothing

  @WS.16 @unhappy
  Scenario: Change a shared tool
    Actor: Founder (L1)
    When I edit a tool that other workflows use
    Then the review warns which other workflows change with it

  @WS.17 @happy
  Scenario: Add a tool at the simplest level
    Actor: Founder (L1)
    When I ask for a new tool
    Then the assistant tries a ready made tool first
    And then a set up tool
    And custom code only when nothing simpler does the job

  @WS.18 @happy
  Scenario: A custom code tool passes its sandbox test
    Actor: Founder (L1)
    Given my custom tool exports an async run function
    When the sandbox test runs
    Then it passes and the tool can be saved

  @WS.19 @unhappy
  Scenario: A custom code tool fails its sandbox test
    Actor: Founder (L1)
    When the code is empty, has no run function, reaches outside the sandbox or has unbalanced braces
    Then the test fails with the reason
    And the tool cannot be saved

  @WS.20 @happy
  Scenario: See and export the workflow diagram
    Actor: Any user
    When I switch to the diagram view
    Then the parts show as a connected diagram
    When I export it
    Then I get a draw.io file

  @WS.21 @unhappy
  Scenario: A routed edit cannot apply when it merges
    Actor: Version service
    Given a studio change request waits for approval
    And its target was removed in the meantime
    When it merges
    Then the pending studio change shows "rejected"
