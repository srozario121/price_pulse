Feature: Product tracking
  As a shopper, I can track retail products so their prices are monitored.

  @PP-E2E-001 @smoke
  Scenario: Add a tracked product
    Given the API is available
    When I add a tracked product with a fixture price of "199.99"
    Then the product is created successfully
    And the product appears in the product list

  @PP-E2E-002
  Scenario: Reject a duplicate product URL
    Given a tracked product with a fixture price of "199.99"
    When I add another product with the same URL
    Then the request is rejected as a conflict

  @PP-E2E-003
  Scenario: Deleting a product removes its price history
    Given a tracked product with a fixture price of "199.99"
    And a synchronous scrape has recorded a price
    When I delete the product
    Then the product's price history is no longer available
