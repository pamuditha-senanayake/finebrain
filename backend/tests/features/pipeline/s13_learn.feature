@pipeline @S13
Feature: S13 Learn
  Every night the Quality Supervisor reviews yesterday's runs. It classifies each failure and drafts fixes.
  A person can also press Skillify to turn a case they handled into a draft skill.

  @S13.01 @happy
  Scenario: The nightly review classifies failures
    Actor: Quality Supervisor (L2)
    Given yesterday had runs that escalated, failed or were denied
    When the nightly review starts at 02:00 Asia/Colombo
    Then each failure gets one class
    And the classes are wrong route, missing knowledge, stale policy, tool error, quality gate failure or access gap

  @S13.02 @happy
  Scenario: Skill health and policy drift are computed
    Actor: Metrics service
    Given yesterday's refund runs
    When health is computed
    Then each skill shows task success, pass^k and conformance to observed runs
    And each policy shows its five freshness signals

  @S13.03 @unhappy
  Scenario: A drifting policy gets an invalidation proposal
    Actor: Quality Supervisor (L2)
    Given observed refunds match the refund policy at 62 percent
    When the drift signal fires
    Then an invalidation proposal is drafted
    And nothing is invalidated without approval at its criticality

  @S13.04 @happy
  Scenario: A fix is drafted on a sandbox branch
    Actor: Quality Supervisor (L2)
    Given a resolver synonym is missing for "money back"
    When the supervisor drafts a fix
    Then a commit lands on a new sandbox branch
    And a change request opens from that branch to main

  @S13.05 @happy
  Scenario: Skillify turns a handled case into a draft skill
    Actor: Customer Care Operator (L3)
    Given the operator took over and closed a late refund conversation
    When the operator presses Skillify
    Then a sandbox branch holds draft skill "refund_late_annual" version 1
    And a C3 change request opens for the DRI

  @S13.06 @unhappy
  Scenario: Skillify on a case no person handled
    Actor: Customer Care Operator (L3)
    Given the agent handled the conversation alone
    When the operator presses Skillify
    Then it is refused with "Skillify needs a case a person handled. Take over first."

  @S13.07 @unhappy
  Scenario: Skillify pressed twice on the same case
    Actor: Customer Care Operator (L3)
    Given the conversation was already skillified
    When the operator presses Skillify again
    Then the same change request is returned
    And no second branch is created

  @S13.08 @happy
  Scenario: Sandbox tests and a replay run before any approval
    Actor: Eval runner
    Given a change request for a new skill is in draft
    When its checks run
    Then the eval suite and trigger evals run in the sandbox
    And a replay shows how many recent runs get a different decision
    And the plain diff, tests and impact preview are attached

  @S13.09 @unhappy @proposed
  Scenario: Sandbox tests fail
    Actor: Eval runner
    Given a draft skill fails 3 of its 18 eval cases
    When the checks finish
    Then the change request stays in "testing"
    And no approval request is created

  @S13.10 @happy
  Scenario: A C0 or C1 change merges by itself
    Actor: Approval service
    Given a C1 resolver synonym fix passed its tests
    When its checks finish
    Then it merges automatically
    And the merge is logged and listed in the morning digest

  @S13.11 @happy
  Scenario: A C2 or higher change waits for its approver
    Actor: Approval service
    Given a C2 skill step edit passed its tests
    When its checks finish
    Then it waits for an L2 steward

  @S13.12 @happy
  Scenario: A shadow run tests a candidate on live traffic
    Actor: Orchestrator
    Given a candidate skill is on staging
    When live refund signals arrive
    Then the candidate runs beside production
    And it never calls an outside tool
    And its decisions are compared with production

  @S13.13 @happy
  Scenario: The morning digest is built
    Actor: Digest job
    Given the nightly review finished
    When the digest is built
    Then it lists runs, failures, fixes applied and changes waiting

  @S13.14 @unhappy @proposed
  Scenario: A quiet night
    Actor: Digest job
    Given yesterday had no failures
    When the digest is built
    Then it says nothing needs a decision
