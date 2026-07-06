Feature: Notification channels
  Triggered alerts deliver via the configured channel; missing channel
  configuration is recorded as a failed delivery.

  @PP-E2E-030
  Scenario: Email channel delivery is recorded as sent
    Given a tracked product with a fixture price of "199.99"
    And an active "below" alert at threshold "150.00" on channel "email"
    When I set the fixture price to "149.99"
    And I run a synchronous scrape
    Then the most recent notification status is "sent"

  @PP-E2E-031
  Scenario: Webhook channel delivery to the sink is recorded as sent
    Given a tracked product with a fixture price of "199.99"
    And an active "below" alert at threshold "150.00" on channel "webhook" with a valid webhook URL
    When I set the fixture price to "149.99"
    And I run a synchronous scrape
    Then the most recent notification status is "sent"

  @PP-E2E-032
  Scenario: Webhook channel without a URL fails
    Given a tracked product with a fixture price of "199.99"
    And an active "below" alert at threshold "150.00" on channel "webhook" with no webhook URL
    When I set the fixture price to "149.99"
    And I run a synchronous scrape
    Then the most recent notification status is "failed"

  @PP-E2E-033
  Scenario: WhatsApp channel delivery is recorded as sent
    Given a tracked product with a fixture price of "199.99"
    And an active "below" alert at threshold "150.00" on channel "whatsapp" with a whatsapp number
    When I set the fixture price to "149.99"
    And I run a synchronous scrape
    Then the most recent notification status is "sent"

  @PP-E2E-034
  Scenario: WhatsApp channel without a number fails
    Given a tracked product with a fixture price of "199.99"
    And an active "below" alert at threshold "150.00" on channel "whatsapp" with no whatsapp number
    When I set the fixture price to "149.99"
    And I run a synchronous scrape
    Then the most recent notification status is "failed"
