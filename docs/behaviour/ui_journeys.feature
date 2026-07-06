Feature: Dashboard UI journeys
  A user can reach the core Price Pulse screens through the composed frontend.

  @PP-E2E-040 @smoke
  Scenario: The dashboard loads
    Given I open the dashboard
    Then I see the "Price Pulse" heading

  @PP-E2E-041
  Scenario: The alert manager screen is reachable
    Given I open the alerts page for product 1
    Then I see the "Price Alerts" heading
    And I see an "Add alert" control

  @PP-E2E-042
  Scenario: The dashboard shows the products area
    Given I open the dashboard
    Then I see the products area
