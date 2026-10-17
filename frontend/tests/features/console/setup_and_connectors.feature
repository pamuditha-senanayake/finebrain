@console @ST
Feature: Setup and connectors
  A short interview teaches the brain about a new business. It asks one question at a time.
  Every connection becomes a sensor, and what it reads flows into knowledge.

  @ST.01 @happy
  Scenario: Teach the brain about the business
    Actor: Founder (L1)
    Given I open Setup
    When I answer the business name, the website and what we do
    And I pick Gmail and Stripe as the tools we use
    And I connect each of them
    And I skip the MCP step
    Then I read that the brain is learning

  @ST.02 @happy
  Scenario: Go back one question
    Actor: Founder (L1)
    Given I am on the tools question
    When I press Back
    Then I see my answer to what we do, ready to edit

  @ST.03 @happy
  Scenario: Connect by signing in
    Actor: Founder (L1)
    When I connect Gmail by signing in and pick the support inbox
    Then the connection shows Connecting, then Reading, then In knowledge

  @ST.04 @happy
  Scenario: Connect a database with a read only link
    Actor: Founder (L1)
    When I connect Postgres with a read only connection string
    Then the connection is saved and starts reading

  @ST.05 @happy
  Scenario: Connect by upload, webhook or website
    Actor: Founder (L1)
    When I connect a tool by uploading export files
    Then the files are read into knowledge
    When I connect a tool by webhook
    Then I get a URL the tool can push events to
    When I connect our website
    Then the brain reads its public pages

  @ST.06 @happy
  Scenario: Add an MCP server
    Actor: Founder (L1)
    When I paste the URL of an MCP server we already use
    Then the brain reads through that server

  @ST.07 @unhappy
  Scenario: The tool is not in the catalog
    Actor: Founder (L1)
    When I type a tool name that is not listed
    Then it is saved as a request
    And it shows "Requested" in the connectors list

  @ST.08 @unhappy
  Scenario: Connect the same thing twice
    Actor: Founder (L1)
    Given the support inbox is already connected
    When I connect the support inbox again
    Then the newer connection replaces the older one
    And the list shows one connection

  @ST.09 @happy
  Scenario: Pause and resume a connection
    Actor: Founder (L1)
    Given Slack is connected
    When I switch it off
    Then it shows "Off" and nothing new is read
    When I switch it on
    Then it starts reading again

  @ST.10 @happy
  Scenario: Disconnect a tool
    Actor: Founder (L1)
    When I disconnect Slack
    Then it leaves the connectors list

  @ST.11 @happy
  Scenario: Use the brain from Claude
    Actor: Any user
    Given I open Use in Claude
    When I copy the server URL or the Claude Code command
    Then I can add the brain as an MCP server in Claude
    And Claude sees only what I may see

  @ST.12 @happy
  Scenario: Choose what Claude may do
    Actor: Founder (L1)
    Given ask, search, read policies and see workflows are on
    And propose changes is off
    When I switch propose changes on
    Then changes Claude proposes go to approvals
    And nothing changes without an approval
