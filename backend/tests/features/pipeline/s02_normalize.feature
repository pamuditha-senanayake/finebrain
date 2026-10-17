@pipeline @S2
Feature: S2 Normalize and protect
  The normalizer turns every raw signal into one canonical Signal.
  It masks personal data on the way. It also stops duplicates.

  @S2.01 @happy
  Scenario: An inbound email becomes a canonical Signal
    Actor: Normalizer
    Given a RawSignalEnvelope for a customer email is on "signals.raw"
    When the normalizer reads it
    Then one Signal with kind "customer_message" and channel "email" is published to "signals.normalized"
    And the Signal carries tenant, cluster, actor, subject and time
    And it links back to the raw event ID

  @S2.02 @happy
  Scenario: Personal data is swapped for vault tokens
    Actor: Normalizer with PII vault
    Given a customer email holds a name, an email address, a phone number, a NIC number and a card fragment
    When the normalizer masks it
    Then each of those values is replaced by a token that starts with "pii_tok_"
    And the vault holds the token to value map
    And the published Signal lists every token in "pii_tokens"

  @S2.03 @happy
  Scenario: A message with no personal data has an empty token list
    Actor: Normalizer
    Given a billing webhook holds no personal data
    When the normalizer reads it
    Then the Signal is published with an empty "pii_tokens" list

  @S2.04 @happy
  Scenario: A document signal also goes to knowledge ingest
    Actor: Normalizer
    Given an uploaded contract arrives on "signals.raw"
    When the normalizer reads it
    Then a Signal with kind "document_arrived" is published to "signals.normalized"
    And the ingest stage receives it as well as the resolver

  @S2.05 @happy
  Scenario: Each attachment becomes its own document signal
    Actor: Normalizer
    Given a customer email has two PDF attachments
    When the normalizer reads it
    Then the email Signal lists both attachments
    And two document Signals are published, one per attachment

  @S2.06 @happy
  Scenario: One customer's messages keep their order
    Actor: Normalizer
    Given customer "C1" sends three emails in a row
    When the normalizer publishes them
    Then all three use the same key on "signals.normalized"
    And consumers read them in the order they were sent

  @S2.07 @unhappy
  Scenario: A duplicate signal stops here
    Actor: Normalizer
    Given a Signal with dedup key "K" was already published
    When another raw signal produces the same dedup key "K"
    Then nothing new is published
    And the duplicate is counted in Sensors health

  @S2.08 @unhappy
  Scenario: The same event is delivered twice by Kafka
    Actor: Normalizer
    Given an envelope with event ID "E" was already processed
    When Kafka delivers event "E" again
    Then the normalizer skips it
    And exactly one Signal exists for event "E"

  @S2.09 @unhappy
  Scenario: A raw body that cannot be parsed goes to the dead letter topic
    Actor: Normalizer
    Given a raw body is broken JSON
    When the normalizer reads it
    Then the envelope goes to "signals.raw.dlq" with the parse error
    And Sensors health shows the failure for that connector

  @S2.10 @unhappy
  Scenario: An older schema version is still accepted
    Actor: Normalizer
    Given the current envelope schema version is N
    When an envelope with schema version N minus 1 arrives
    Then the normalizer reads it as usual

  @S2.11 @unhappy
  Scenario: A schema version two steps old is refused
    Actor: Normalizer
    Given the current envelope schema version is N
    When an envelope with schema version N minus 2 arrives
    Then it goes to "signals.raw.dlq" with reason "unsupported_schema_version"

  @S2.12 @unhappy @proposed
  Scenario: The vault is down so nothing leaves unmasked
    Actor: Normalizer with PII vault
    Given the PII vault is unreachable
    When a customer email with personal data is read
    Then no Signal is published
    And the envelope is retried later
    And no unmasked value appears on any topic
