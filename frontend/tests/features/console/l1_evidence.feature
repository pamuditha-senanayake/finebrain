@console @EV
Feature: L1 Evidence requests
  When the brain needs proof, it asks the DRI early. The DRI uploads files or grants a source.
  A grant always shows its scope, retention and revoke path first.

  @EV.01 @happy
  Scenario: Upload the requested evidence
    Actor: Finance Director (L1)
    Given the brain asked me for the September bank statement
    When I upload the file
    Then the request shows fulfilled
    And the obligation readiness updates

  @EV.02 @unhappy
  Scenario: Upload to a request that is already fulfilled
    Actor: Finance Director (L1)
    Given the bank statement request is fulfilled
    When I try to upload again
    Then I read "Already fulfilled"

  @EV.03 @happy
  Scenario: Read a grant before giving it
    Actor: Finance Director (L1)
    Given the brain suggests granting the finance inbox
    When I open the grant
    Then I see the scope, the 90 day retention, the agents that will use it and how to revoke

  @EV.04 @happy
  Scenario: Request a grant
    Actor: Finance Director (L1)
    When I request the finance inbox grant
    Then a C4 approval waits for two L1 approvers
    And the evidence request shows it waits for the grant

  @EV.05 @unhappy
  Scenario: A grant approval is rejected
    Actor: Founder (L1)
    Given the finance inbox grant waits for approval
    When I reject it
    Then the grant is not active
    And the evidence request stays open

  @EV.06 @happy
  Scenario: Revoke a grant
    Actor: Security Officer (L2)
    Given the finance inbox grant is active
    When I revoke it
    Then the agent loses access and the sensor stops
