@pipeline @S4
Feature: S4 Orchestrate
  Each task runs as one durable workflow. The workflow survives restarts and long waits.
  A retry can never start the same task twice.

  @S4.01 @happy
  Scenario: A task starts one workflow and opens a run
    Actor: Orchestrator
    Given a TaskRequest with task ID "T1" is on "tasks.created"
    When the orchestrator reads it
    Then one durable workflow starts with workflow ID "T1"
    And one Run row is created
    And the console receives a live "run started" event

  @S4.02 @unhappy
  Scenario: The same task is delivered twice
    Actor: Orchestrator
    Given a workflow with ID "T1" is already running
    When "tasks.created" delivers task "T1" again
    Then no second workflow starts
    And one Run exists for "T1"

  @S4.03 @happy
  Scenario: A release in the middle of a run does not change the skill
    Actor: Orchestrator
    Given run "R1" pinned skill "refund_standard" version 4
    When version 5 is released while "R1" is still running
    Then "R1" finishes on version 4

  @S4.04 @unhappy
  Scenario: A worker crashes in the middle of a run
    Actor: Orchestrator
    Given run "R1" finished its retrieval step
    When the worker process stops
    Then a new worker resumes "R1" from its history
    And the retrieval step does not run again
