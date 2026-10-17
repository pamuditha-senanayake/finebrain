@console @LR
Feature: L2 Loops and readiness
  Every function is a loop of sensor, policy, tool, gate and learning. Experiments make loops better.
  The readiness scheduler finds missing evidence before deadlines.

  @LR.01 @happy
  Scenario: Run a website experiment to the end
    Actor: AI Operations Lead (L2)
    Given Clarity found 312 rage clicks on the pricing toggle
    When I preview the fix on a sandbox branch
    And I start the A/B experiment
    And I conclude it
    And I keep and ship the winner
    Then the learning is recorded
    And the pricing change goes to L1 for approval

  @LR.02 @happy
  Scenario: Discard an experiment
    Actor: AI Operations Lead (L2)
    Given an experiment was concluded
    When I discard it
    Then its sandbox branch is abandoned
    And the result is still kept as learning

  @LR.03 @unhappy
  Scenario: Start an experiment without a preview
    Actor: AI Operations Lead (L2)
    Given an experiment is only proposed
    When I try to start it
    Then I read "Preview on a sandbox branch first"

  @LR.04 @unhappy
  Scenario: Preview an experiment twice
    Actor: AI Operations Lead (L2)
    Given an experiment was already previewed
    When I preview it again
    Then I read "Already previewed"

  @LR.05 @unhappy
  Scenario: Conclude an experiment that is not running
    Actor: AI Operations Lead (L2)
    Given an experiment is previewed but not started
    When I try to conclude it
    Then I read "Experiment is not running"

  @LR.06 @unhappy
  Scenario: Keep an experiment before it is concluded
    Actor: AI Operations Lead (L2)
    Given an experiment is still running
    When I try to keep it
    Then I read "Conclude the experiment first"

  @LR.07 @unhappy
  Scenario: Discard an experiment with nothing to discard
    Actor: AI Operations Lead (L2)
    Given an experiment is only proposed
    When I try to discard it
    Then I read "Nothing to discard"

  @LR.08 @unhappy
  Scenario: An operator tries to start an experiment
    Actor: Customer Care Operator (L3)
    When I try to start a previewed experiment
    Then I read "Starting an experiment needs L2 or L1"

  @LR.09 @happy
  Scenario: Read a loop canvas
    Actor: AI Operations Lead (L2)
    When I open the Website UX loop
    Then I see each stage with its live metric, run history, pending gates and experiments

  @LR.10 @happy
  Scenario: Find missing evidence before a deadline
    Actor: Knowledge Steward (L2)
    When I run the readiness scheduler
    Then each gap shows one action: dispatch an agent, ask the DRI or request a source
