@console @PS
Feature: L2 Policies, skills and agents
  Policies say what is allowed. Skills say how work is done. Agents move up in autonomy step by step.
  Main never changes directly. Every edit is a draft with its own change request.

  @PS.01 @happy
  Scenario: Travel in time through a policy
    Actor: Knowledge Steward (L2)
    Given I open the refund window policy
    When I drag the as of slider back in time
    Then I see what was true then and what the brain believed then

  @PS.02 @unhappy
  Scenario: A policy is drifting
    Actor: Knowledge Steward (L2)
    Given observed refunds no longer match the policy well
    When I open the refund window policy
    Then the freshness signals warn that it is drifting
    And an invalidation proposal waits for approval

  @PS.03 @happy
  Scenario: Change a policy from its page
    Actor: Knowledge Steward (L2)
    When I press change in studio on the refund window policy
    Then Workflow Studio opens with that policy in focus

  @PS.04 @happy
  Scenario: Improve a skill safely
    Actor: AI Operations Lead (L2)
    Given skills are sorted by conformance, weakest first
    When I edit step 2 of "Refund inside policy"
    And I save it as a draft
    Then a change request opens on a sandbox branch with a before and after diff

  @PS.05 @unhappy
  Scenario: An operator tries to author a skill
    Actor: Customer Care Operator (L3)
    When I try to save a skill draft
    Then I read "Skills are authored at L2"

  @PS.06 @happy
  Scenario: Read a skill's demand
    Actor: AI Operations Lead (L2)
    When I open a skill
    Then I see its steps, health and demand over time in read only form

  @PS.07 @happy
  Scenario: Promote an agent
    Actor: AI Operations Lead (L2)
    Given the Billing Agent is supervised
    When I propose promoting it
    Then a change request to make it autonomous opens at the matrix criticality

  @PS.08 @unhappy
  Scenario: Promote an agent that is already autonomous
    Actor: AI Operations Lead (L2)
    Given the Care Agent is autonomous
    When I try to promote it
    Then I read "Already autonomous"

  @PS.09 @unhappy
  Scenario: An operator tries to promote an agent
    Actor: Customer Care Operator (L3)
    When I try to promote an agent
    Then I read "Promotions are proposed at L2"
