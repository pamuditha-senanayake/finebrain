// Error reporting adapter. The console sink runs now; register a vendor sink (for example Sentry) later.
type Sink = (error: unknown, context?: Record<string, unknown>) => void;

const sinks: Sink[] = [
  (error, context) => {
    if (process.env.NODE_ENV !== "test") console.warn("[report]", error, context ?? "");
  },
];

export function registerErrorSink(sink: Sink) {
  sinks.push(sink);
}

export function reportError(error: unknown, context?: Record<string, unknown>) {
  for (const sink of sinks) {
    try {
      sink(error, context);
    } catch {
      // A broken sink must never break the app.
    }
  }
}
