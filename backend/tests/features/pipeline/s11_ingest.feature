@pipeline @S11
Feature: S11 Ingest knowledge
  Documents become knowledge here. Each one is filed, parsed, chunked and embedded.
  Then candidate facts are pulled out with their exact evidence.

  @S11.01 @happy
  Scenario: A document is filed by the filing rules
    Actor: Ingest service
    Given a pricing PDF arrives as a document Signal
    When the filing rules run
    Then the document gets a cluster, a type, a sensitivity, a retention and ACL labels
    And "docs.filed" carries it

  @S11.02 @happy
  Scenario: Text, tables and scanned pages are extracted
    Actor: Ingest service
    Given a filed invoice has a table and one scanned page
    When the text is extracted
    Then the table rows and the scanned text are both in the output
    And "docs.extracted" carries it

  @S11.03 @happy
  Scenario: Chunks are embedded with their access labels
    Actor: Ingest service
    Given extracted text from a "confidential" contract
    When it is chunked and embedded
    Then every chunk carries the "confidential" label and a full text index

  @S11.04 @happy
  Scenario: Candidate facts are extracted with exact evidence
    Actor: Ingest service
    Given the pricing PDF says "Refund window for annual plans is 14 days"
    When candidate facts are extracted
    Then a FactCandidate holds that statement, its subject, value and valid time
    And its evidence points to the document, page and span
    And it is published to "facts.candidates"

  @S11.05 @unhappy
  Scenario: A candidate with low confidence
    Actor: Ingest service
    Given the extractor is not confident about a value
    When the candidate is published
    Then it is marked "unverified"
    And it goes to the librarian queue

  @S11.06 @unhappy @proposed
  Scenario: A document cannot be parsed
    Actor: Ingest service
    Given an uploaded file is corrupted
    When extraction fails
    Then the Library shows extraction status "failed" with the reason
    And no facts are drafted from it

  @S11.07 @unhappy @proposed
  Scenario: No filing rule matches a document
    Actor: Ingest service
    Given no filing rule fits a new document
    When it is filed
    Then it gets the "restricted" label by default
    And it appears in the librarian queue as an orphan document
