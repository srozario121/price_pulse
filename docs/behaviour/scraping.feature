Feature: Price scraping and deduplication
  Scrapes record a price for a tracked product and deduplicate unchanged pages.

  @PP-E2E-010 @smoke
  Scenario: A synchronous scrape records the current price
    Given a tracked product with a fixture price of "199.99"
    When I run a synchronous scrape
    Then the latest recorded price is "199.99"

  @PP-E2E-011
  Scenario: Identical page content is deduplicated
    Given a tracked product with a fixture price of "199.99"
    When I run a synchronous scrape
    And I run a synchronous scrape
    Then the price history contains 1 record

  @PP-E2E-012
  Scenario: A changed price produces a new record
    Given a tracked product with a fixture price of "199.99"
    When I run a synchronous scrape
    And I set the fixture price to "149.99"
    And I run a synchronous scrape
    Then the price history contains 2 records
    And the latest recorded price is "149.99"

  @PP-E2E-013 @smoke
  Scenario: A scheduled scrape records a price via the beat cadence
    Given a tracked product with a fixture price of "199.99"
    When I wait for a scheduled scrape to run
    Then the price history contains at least 1 record
