@console @RC
Feature: Research Console
  The research program has its own console. It only reads. It can be removed without touching the product.

  @RC.01 @happy
  Scenario: Monitor research metrics
    Actor: Research Analyst (L2)
    When I open the Research Console
    Then metrics for skills, policies, security and integration are labelled SAMPLE

  @RC.02 @unhappy
  Scenario: Export sample values
    Actor: Research Analyst (L2)
    When I try to export sample values as results
    Then the export is refused

  @RC.03 @unhappy
  Scenario: A product user opens the console
    Actor: Customer Care Operator (L3)
    When I open the research address
    Then I see the permission denied state

  @RC.04 @happy
  Scenario: The console is switched off
    Actor: Any user
    Given the research flag is off
    When I use the product
    Then no research page or link exists
    And every product screen still works
