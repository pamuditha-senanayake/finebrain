@console @L3
Feature: L3 Operations floor
  Agents do the work through APIs. Operators watch them live and step in when needed.
  Any case a person handles can become a skill.

  @L3.01 @happy
  Scenario: Watch the agent fleet
    Actor: Customer Care Operator (L3)
    When I open Fleet
    Then every agent shows live status, queue, errors and cost
    When I switch to the grid
    Then a moving orb means an agent is working now

  @L3.02 @happy
  Scenario: Filter the fleet
    Actor: Customer Care Operator (L3)
    When I filter the fleet by category and workflow
    Then only matching agents remain

  @L3.03 @happy
  Scenario: Read an agent profile
    Actor: Customer Care Operator (L3)
    When I open the Refund Agent
    Then I see its sensors, skills, policies, capabilities, templates and autonomy
    And its running history shows each run with its actor and input

  @L3.04 @happy
  Scenario: Inspect a run step by step
    Actor: Customer Care Operator (L3)
    When I filter Runs for customer 1042 and open the refund run
    Then each step is labelled model judgment or deterministic call
    And retrieved facts show their valid time
    And the escalation says exactly why the agent stopped

  @L3.05 @happy
  Scenario: Mark a run as wrong
    Actor: Customer Care Operator (L3)
    When I mark a run wrong with a note
    Then the run and the agent show the mistake
    And the agent's DRI is notified

  @L3.06 @unhappy
  Scenario: Mark a run wrong with no note
    Actor: Customer Care Operator (L3)
    When I mark a run wrong and leave the note empty
    Then I read "Say what went wrong"

  @L3.07 @unhappy
  Scenario: Mark a run wrong twice
    Actor: Customer Care Operator (L3)
    Given the run is already marked wrong
    When I mark it wrong again
    Then I read "Already marked wrong"

  @L3.08 @happy
  Scenario: Find a conversation
    Actor: Customer Care Operator (L3)
    When I search conversations for "refund"
    Then only matching conversations remain
    When I open the needs a human tab
    Then only conversations waiting for a person remain

  @L3.09 @happy
  Scenario: Take over, reply and hand back
    Actor: Customer Care Operator (L3)
    Given a live conversation shows the agent's reasoning and proposed actions
    When I take over
    And I reply to the customer
    Then my reply appears in the transcript
    When I hand back
    Then the agent continues the conversation

  @L3.10 @unhappy
  Scenario: Reply without taking over
    Actor: Customer Care Operator (L3)
    When I try to reply in a conversation the agent holds
    Then I read "Take over the conversation before replying"

  @L3.11 @unhappy
  Scenario: Send an empty reply
    Actor: Customer Care Operator (L3)
    Given I took over a conversation
    When I send an empty message
    Then I read "Message is empty"

  @L3.12 @unhappy
  Scenario: Take over a closed conversation
    Actor: Customer Care Operator (L3)
    Given the conversation is closed
    When I try to take over
    Then I read "Conversation is closed"

  @L3.13 @happy
  Scenario: Handle an escalation, then Skillify it
    Actor: Customer Care Operator (L3)
    Given the escalations queue is sorted by risk and waiting time
    When I open the refund request from customer 1042
    And I take over and reply myself
    And I close the conversation
    And I press Skillify
    Then my handling becomes a draft skill on a sandbox branch for L2 to test

  @L3.14 @unhappy
  Scenario: Skillify before taking over
    Actor: Customer Care Operator (L3)
    Given the agent handled the conversation alone
    When I press Skillify
    Then I read "Skillify needs a case a person handled. Take over first."

  @L3.15 @happy
  Scenario: Check the template board
    Actor: Customer Care Operator (L3)
    When I filter the template board to stale
    Then I see which fields are old, who filled them and from which source
