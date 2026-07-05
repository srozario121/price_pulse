Feature: Price alerts
  A price crossing an alert threshold dispatches a notification, subject to a
  cooldown that suppresses repeat notifications until it is reset.

  @PP-E2E-020 @smoke
  Scenario: A price drop below the threshold triggers a notification
    Given a tracked product with a fixture price of "199.99"
    And an active "below" alert at threshold "150.00" on channel "email"
    When I set the fixture price to "149.99"
    And I run a synchronous scrape
    Then the alert has 1 notification
    And the most recent notification status is "sent"

  @PP-E2E-021
  Scenario: A price that does not cross the threshold does not notify
    Given a tracked product with a fixture price of "199.99"
    And an active "below" alert at threshold "150.00" on channel "email"
    When I run a synchronous scrape
    Then the alert has 0 notifications

  @PP-E2E-022
  Scenario: Cooldown suppresses a repeat notification until reset
    Given a tracked product with a fixture price of "199.99"
    And an active "below" alert at threshold "150.00" on channel "email"
    When I set the fixture price to "149.99"
    And I run a synchronous scrape
    And I set the fixture price to "148.99"
    And I run a synchronous scrape
    Then the alert has 1 notification
    When I reset the alert cooldown
    And I set the fixture price to "147.99"
    And I run a synchronous scrape
    Then the alert has 2 notifications
