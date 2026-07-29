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

  # The unit tests mock the API, so they can only catch a contract mismatch if the
  # mock happens to mirror the real constraint. This one talks to the real backend
  # through the composed nginx stack, which is what makes it able to catch a
  # request the API rejects — the chart shipped permanently blank because it asked
  # for limit=200 against an endpoint capped at 100, and nothing noticed.
  @PP-E2E-046 @smoke
  Scenario: The price chart plots a real scraped price
    Given a product that has been scraped and has a recorded price
    When I open that product's detail page
    Then the price chart plots at least one point
    And the chart does not report an error or missing data
