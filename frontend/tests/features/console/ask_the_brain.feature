@console @AB
Feature: Ask the Brain
  Anyone can ask the brain a question in plain words, by typing or by voice.
  Answers use only what the asker may see. Each one cites its source and when it is true.

  @AB.01 @happy
  Scenario: Ask about the page I am on
    Actor: Any user
    Given I am on the refund window policy page
    When I type "Why is this policy drifting?"
    Then the brain asks whether I mean this page or the whole system
    When I choose this page
    Then I get a plain answer with numbered citations about that policy

  @AB.02 @happy
  Scenario: Ask about the whole system
    Actor: Head of Customer Success (L1)
    When I ask "What is our refund window?" for the whole system
    Then I get a plain answer with numbered citations
    And each citation shows when the fact is true

  @AB.03 @happy
  Scenario: A suggested question already knows its scope
    Actor: Any user
    When I tap a suggested question
    Then the brain answers without asking for the scope

  @AB.04 @unhappy
  Scenario: The answer needs facts I may not see
    Actor: Customer Care Operator (L3)
    When I ask about the finance director's tax evidence
    Then the answer cites none of the restricted facts
    And it says some sources are locked for me

  @AB.05 @unhappy @proposed
  Scenario: The brain does not know
    Actor: Any user
    When I ask about something no fact covers
    Then the brain says it does not know
    And it does not make up an answer

  @AB.06 @happy
  Scenario: Ask by voice
    Actor: Founder (L1)
    Given I am on the Ask page
    When I tap the orb and ask a question aloud
    Then my words appear as text
    And the answer is spoken back and shown with citations

  @AB.07 @unhappy
  Scenario: The microphone is blocked
    Actor: Founder (L1)
    Given the browser blocks the microphone
    When I tap the orb
    Then I read "The microphone is blocked. Allow it in the browser, or type instead."

  @AB.08 @unhappy
  Scenario: Nothing was heard
    Actor: Founder (L1)
    When I tap the orb and stay silent
    Then I read "I did not hear anything. Tap to try again."

  @AB.09 @unhappy
  Scenario: The recording is too long
    Actor: Founder (L1)
    When I record more than about two minutes
    Then the recording is refused with "The recording is too long."

  @AB.10 @unhappy
  Scenario: The voice service fails
    Actor: Founder (L1)
    Given the voice service is down
    When I ask aloud
    Then I see that voice failed
    And I can type the question instead
