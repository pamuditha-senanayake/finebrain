@console @KN
Feature: L2 Knowledge
  Stewards keep the brain worth asking. The vault holds verified facts with their proof.
  The Library, Resolver, Templates and Sensors show what sits behind every answer.

  @KN.01 @happy
  Scenario: Resolve a knowledge conflict
    Actor: Knowledge Steward (L2)
    Given the librarian queue shows a refund window conflict
    When I ask the Librarian to propose a resolution
    Then one change request updates the policy and every dependent
    When I run the checks
    Then the change is C3 and waits for the L1 DRI

  @KN.02 @unhappy
  Scenario: Ask for a proposal twice
    Actor: Knowledge Steward (L2)
    Given the Librarian already proposed a resolution for this item
    When I ask again
    Then I read "Already proposed"

  @KN.03 @happy
  Scenario: Read a fact with its proof
    Actor: Knowledge Steward (L2)
    When I open a fact in the vault
    Then I see its evidence, valid time, recorded time, verifier and dependents

  @KN.04 @happy
  Scenario: Work the other queue items
    Actor: Knowledge Steward (L2)
    When I filter the librarian queue to stale, duplicate, orphan or unverified items
    Then each item shows the proposed action

  @KN.05 @happy
  Scenario: Browse the Library
    Actor: Knowledge Steward (L2)
    When I filter the Library by cluster, type and sensitivity
    Then each document shows extraction status, linked facts and retention

  @KN.06 @happy
  Scenario: Check routing in the Resolver
    Actor: AI Operations Lead (L2)
    When I open the Resolver
    Then each event routes to an agent and a skill
    And trigger evals show the right skill fires

  @KN.07 @happy
  Scenario: Read the information templates
    Actor: AI Operations Lead (L2)
    When I open Templates
    Then each template shows fields, source sensors, freshness rule, cadence, owner and agents

  @KN.08 @happy
  Scenario: Check sensor health
    Actor: AI Operations Lead (L2)
    When I open Sensors
    Then each sensor shows health, subscribers, scopes, retention and a personal data flag

  @KN.09 @happy
  Scenario: Switch a sensor off
    Actor: AI Operations Lead (L2)
    When I switch the review sites sensor off
    Then it shows "Off"
    And its subscribers stop receiving its events

  @KN.10 @happy
  Scenario: Filter overview pages by workflow
    Actor: AI Operations Lead (L2)
    When I pick the refunds workflow on Policies, Skills or Sensors
    Then only items in that workflow remain
