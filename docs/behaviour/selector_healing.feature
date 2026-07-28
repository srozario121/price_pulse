@selector-healing @live-llm
Feature: Self-healing price selectors when a retailer's markup drifts
  As an operator
  I want a source whose markup has changed to repair its own price selector
  So that a retailer's redesign degrades one scrape cycle instead of every
  scrape from then on

  # These scenarios call a REAL LLM provider and spend money, so they are tagged
  # @live-llm and excluded from `make test-e2e` / `make test-e2e-smoke` and from
  # CI. Run them deliberately with `make test-e2e-llm` and a key in .env.
  #
  # The whole loop is asserted through the public API and the observable scrape
  # outcome — never by reading the selector_profile table — so what is proven is
  # the behaviour a user experiences, not an internal state transition.

  Background:
    Given the e2e stack is running

  @PP-E2E-043
  Scenario: A page whose markup has drifted records a selector miss, not a generic failure
    Given a tracked product whose fixture page uses drifted markup
    When the product is scraped synchronously
    Then the latest price record has extraction status "selector_miss"
    And the latest price record has no price

  @PP-E2E-044
  Scenario: Reporting a selector issue heals the source end to end
    Given a tracked product whose fixture page uses drifted markup
    And the product has been scraped and recorded a selector miss
    When a selector issue is reported for the product
    Then the report is accepted and regeneration is enqueued
    And within 120 seconds a fresh scrape of the same unchanged page records "ok"
    And the recorded price matches the price the fixture page is serving

  @PP-E2E-045
  Scenario: A healed selector is reused without calling the provider again
    Given a tracked product whose fixture page uses drifted markup
    And the product's selector has been healed
    When the fixture price changes to "321.99"
    And the product is scraped synchronously
    Then the latest price record has extraction status "ok"
    And the recorded price is "321.99"
