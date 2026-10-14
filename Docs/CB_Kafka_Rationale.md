# Why Company Brain uses Kafka

## The short answer

Company Brain reacts to events. A payment fails. An email arrives. A skill gets released. Each event must reach several services, in order, without loss. Kafka is built for exactly that job.

PostgreSQL is built for a different job. It stores the truth and answers questions about it. So we use both, and each one does what it does best.

## What Kafka does here

Kafka is the event backbone between the fifteen pipeline stages. A stage never calls the next stage directly. Instead, it writes an event to a topic. The next stage reads from that topic at its own pace. As a result, the stages stay independent, and one slow stage never blocks the rest.

| Responsibility | How it works in Company Brain |
|---|---|
| Carry signals | Capture writes every webhook as an envelope to `signals.raw`. The raw body stays in S3. |
| Fan out | One event on `signals.normalized` feeds the resolver and the ingest service at the same time. |
| Keep order | Keys start with the tenant id and subject. So events for one customer arrive in order. |
| Absorb bursts | A flood of webhooks waits safely in the log. Consumers catch up without dropping anything. |
| Replay | Events stay for 1 to 30 days. A fixed consumer can reread them from any offset. |
| Isolate failures | A bad message moves to `{topic}.dlq`. Meanwhile, the rest of the stream keeps flowing. |
| Broadcast releases | `graph.released` is a compacted topic. Every service reloads the latest graph version from it. |
| Feed the screen | `ui.events` streams to the SSE gateway. Then the console updates live. |

## Why not PostgreSQL alone

PostgreSQL could hold a queue table. Many small systems do this, and it works at first. However, it breaks down as Company Brain grows.

First, polling is expensive. Every consumer would query the table again and again. That load hits the same database that serves the console and the agents.

Second, fan out is hard. Kafka lets each consumer group keep its own position in one shared log. A table queue needs a copy per consumer, or complex tracking columns.

Third, replay is hard. Once a row is consumed and deleted, it is gone. Kafka keeps the history, so a replay is just a reset of the offset.

Fourth, scale is uneven. Partitions let us add consumers for a busy tenant. A table queue, by contrast, becomes a lock hotspot.

Finally, failure would spread. If the database slows down, a table queue slows with it. With Kafka, capture keeps accepting signals even while a downstream stage recovers.

## How the two work together

PostgreSQL remains the system of record. Kafka never decides what is true. It only carries news about change.

The outbox pattern joins them safely. A service writes its state change and an outbox row in one database transaction. A relay then publishes that row to Kafka. So an event exists only if the state change committed. Nothing is lost between the two.

Consumers are also idempotent. Kafka delivers at least once, so a message may arrive twice. Therefore each consumer checks a key in Valkey first and skips duplicates.

## The rule to remember

Every byte has one home. PostgreSQL holds the truth. Kafka holds events in motion for a limited time. Valkey holds what can be rebuilt. S3 holds raw and large content.

Locally, Redpanda runs the same Kafka API on port 9092. In production, we use Amazon MSK or Confluent.
