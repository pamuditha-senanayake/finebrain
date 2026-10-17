@console @SH
Feature: Shell and navigation
  Every screen shares one shell. It shows who you are, which environment you are in and where you can go.
  Higher tiers can look down, never up.

  @SH.01 @happy
  Scenario: Pick a persona and land on its home
    Actor: Any user
    Given I open Company Brain
    When I choose the head of customer success from the persona menu
    Then I land on L1 Command
    And the sidebar shows only L1 sections

  @SH.02 @happy
  Scenario: A higher tier looks down
    Actor: Founder (L1)
    Given I am the founder
    When I open the L3 escalations queue
    Then I see the queue

  @SH.03 @unhappy
  Scenario: A lower tier tries to look up
    Actor: Customer Care Operator (L3)
    Given I am the care operator
    When I open the L1 approvals address directly
    Then I see the permission denied state
    And no approval data is shown

  @SH.04 @happy
  Scenario: The environment is always visible
    Actor: Any user
    When I open any screen on Production
    Then a band says Production
    When I open a sandbox branch
    Then the band names that sandbox branch

  @SH.05 @happy
  Scenario: Jump anywhere with the command palette
    Actor: Any user
    When I press Cmd K and type "Refund Agent"
    And I pick the agent
    Then its profile opens

  @SH.06 @unhappy
  Scenario: The palette finds nothing
    Actor: Any user
    When I press Cmd K and type "zzzz"
    Then the palette says there are no results

  @SH.07 @happy
  Scenario: Read notifications
    Actor: Any user
    Given I have three unread notifications
    When I open one
    Then it is marked read and the count drops to two
    When I choose mark all read
    Then the count is zero

  @SH.08 @happy
  Scenario: Switch tenant
    Actor: Founder (L1)
    When I switch the tenant to "Scale Demo"
    Then lists show hundreds of agents and stay responsive

  @SH.09 @happy
  Scenario: Planned clusters show as placeholders
    Actor: Founder (L1)
    When I open the cluster switcher
    Then People, Product Engineering and Procurement show as planned

  @SH.10 @happy
  Scenario: Switch between light and dark themes
    Actor: Any user
    When I choose the dark theme
    Then every screen uses the dark palette
    And my choice is kept next time

  @SH.11 @happy
  Scenario: Demo data is labelled
    Actor: Any user
    Given the console runs on mock data
    Then a "Demo data" badge is visible

  @SH.12 @unhappy
  Scenario: A list fails to load
    Actor: Any user
    Given the API returns an error for runs
    When I open Runs
    Then I see the error state with a retry button
    When I retry and the API answers
    Then the runs appear

  @SH.13 @unhappy
  Scenario: A list is empty
    Actor: Any user
    Given there are no escalations
    When I open Escalations
    Then I see a short empty state
