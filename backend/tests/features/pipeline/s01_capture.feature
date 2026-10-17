@pipeline @S1
Feature: S1 Capture
  A source system sends something new. The capture stage checks it first.
  Then it stores the raw body once and publishes a small pointer to Kafka.
  The raw body never travels on Kafka.

  @S1.01 @happy
  Scenario: A verified webhook is stored and published
    Actor: Connector service
    Given tenant "Finebase Labs" granted the Gmail source with scope "support inbox"
    When Gmail pushes a new message with a valid signature
    Then the raw body is written to object storage under its SHA256 hash
    And one RawSignalEnvelope is published to "signals.raw"
    And the envelope holds the raw object URI and not the raw body

  @S1.02 @happy
  Scenario: A poll worker captures a daily Clarity export
    Actor: Connector service
    Given the Clarity source is granted with a daily poll
    When the poll worker runs its daily request
    Then each new export row is stored once in object storage
    And one envelope per export is published to "signals.raw" with source type "clarity_export"
    And the poll cursor moves past the captured rows

  @S1.03 @happy
  Scenario: A person uploads a document
    Actor: DRI
    Given the DRI has an open evidence request
    When the DRI uploads an invoice PDF
    Then the file is stored in object storage under its SHA256 hash
    And one envelope with source type "upload" is published to "signals.raw"

  @S1.04 @happy
  Scenario: The same body arriving twice is stored once
    Actor: Connector service
    Given a raw body was already stored under its SHA256 hash
    When the same body arrives again with the same external ID
    Then object storage still holds one copy
    And no second envelope is published

  @S1.05 @unhappy
  Scenario: A webhook with a bad signature is rejected
    Actor: Connector service
    When a webhook arrives with a signature that does not verify
    Then the capture service answers 401
    And nothing is written to object storage
    And nothing is published to "signals.raw"

  @S1.06 @unhappy
  Scenario: Many bad signatures raise an alert
    Actor: Connector service
    When 10 webhooks with bad signatures arrive within 5 minutes
    Then an alert is raised for that connector
    And every one of them is still rejected with 401

  @S1.07 @unhappy
  Scenario: A signal from a scope the tenant never granted is dropped
    Actor: Connector service
    Given the tenant did not grant the "finance inbox" scope
    When a message arrives from the finance inbox
    Then the signal is dropped before storage
    And the drop is logged with the connector and the missing scope

  @S1.08 @unhappy
  Scenario: A signal from a revoked grant is dropped
    Actor: Connector service
    Given the finance inbox grant was revoked
    When a message arrives from the finance inbox
    Then the signal is dropped before storage
    And the drop is logged with the revoked grant ID

  @S1.09 @unhappy
  Scenario: A paused connection captures nothing
    Actor: Connector service
    Given the Slack connection is switched off
    When a new Slack message is posted
    Then nothing is stored and nothing is published
    And the connection shows "Off" in the connectors list

  @S1.10 @unhappy
  Scenario: Kafka is down when a webhook arrives
    Actor: Connector service
    Given Kafka is unavailable
    When a verified webhook arrives
    Then the capture service answers 503 so the source retries later
    And no envelope is lost once Kafka is back

  @S1.11 @unhappy
  Scenario: Kafka is down during a poll
    Actor: Connector service
    Given Kafka is unavailable
    When the poll worker runs
    Then the local cursor does not move past unpublished rows
    And the next poll publishes the missed rows once Kafka is back

  @S1.12 @unhappy
  Scenario: A body larger than 25 MB goes to the upload path
    Actor: Connector service
    When a signal arrives with a body larger than 25 MB
    Then it is not published as a normal envelope
    And it is handed to the upload path

  @S1.13 @unhappy
  Scenario: Only allowlisted headers are kept
    Actor: Connector service
    When a webhook arrives with headers outside the allowlist
    Then the envelope keeps only allowlisted headers in "headers_subset"
