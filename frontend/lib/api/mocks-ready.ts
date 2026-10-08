import { reportError } from "@/lib/errors";
import { flags } from "@/lib/flags";

let ready: Promise<void> | null = null;

/** Starts the MSW worker once per page. Every API call awaits this, so nothing races the worker. */
export function mocksReady(): Promise<void> {
  if (!flags.mocks || typeof window === "undefined") return Promise.resolve();
  ready ??= import("@/lib/mock/browser")
    .then(({ worker }) => worker.start({ onUnhandledRequest: "bypass", quiet: true, serviceWorker: { url: "/mockServiceWorker.js" } }))
    .then(() => undefined)
    .catch((e) => {
      // Hot reload re-runs this module while the worker is still enabled. That is fine.
      if (!String(e).includes("already enabled")) reportError(e, { where: "msw start" });
    });
  return ready;
}
