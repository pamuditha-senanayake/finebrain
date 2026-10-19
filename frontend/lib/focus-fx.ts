// focus-fx.ts: what happens when something is shown (step 11). Find the marked element, scroll it to the middle, lock on
// (brackets, sweep, glow: see app/focus.css), and scan a found sentence in word by word with the CSS Custom Highlight
// API. Plain DOM, no React. Used by components/shell/focus-runner.tsx. Honours prefers-reduced-motion.
import type { FocusTarget } from "./focus";

// Config
const WAIT_MS = 6000; // how long to wait for a page's data to put the element on screen
const LOCK_MS = 3800;
const SCAN_MS = 650;
const HOLD_MS = 2400;
const DIM_MS = 900;
const SETTLE_MS = 160; // after the scroll, before the lock-on starts

const still = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const canHighlight = () => typeof CSS !== "undefined" && "highlights" in CSS && typeof Highlight !== "undefined";

export function findFocus(kind: string, id: string): HTMLElement | null {
  const wanted = `${kind}:${id}`.replaceAll("\\", "\\\\").replaceAll('"', '\\"');
  return document.querySelector<HTMLElement>(`[data-focus-id="${wanted}"]`);
}

/** Resolves with the element once the page shows it, or null after WAIT_MS. */
export function whenShown(kind: string, id: string, signal: AbortSignal): Promise<HTMLElement | null> {
  return new Promise((resolve) => {
    const now = findFocus(kind, id);
    if (now) return resolve(now);
    const done = (el: HTMLElement | null) => {
      observer.disconnect();
      clearTimeout(timer);
      resolve(el);
    };
    const observer = new MutationObserver(() => {
      const el = findFocus(kind, id);
      if (el) done(el);
    });
    const timer = setTimeout(() => done(null), WAIT_MS);
    signal.addEventListener("abort", () => done(null));
    observer.observe(document.body, { childList: true, subtree: true });
  });
}

/** Brackets close in, a light crosses, the edge glows twice. The element is positioned for the effect and put back after. */
export function lockOn(el: HTMLElement): () => void {
  const wasStatic = getComputedStyle(el).position === "static";
  if (wasStatic) el.style.position = "relative";
  el.removeAttribute("data-focus-lock");
  void el.offsetWidth; // restart the animation if the same element is shown twice
  el.setAttribute("data-focus-lock", "");
  const end = () => {
    el.removeAttribute("data-focus-lock");
    if (wasStatic) el.style.position = "";
  };
  const timer = setTimeout(end, LOCK_MS);
  return () => {
    clearTimeout(timer);
    end();
  };
}

/** The text range from character `start` to `end` of the element's own text. */
function rangeAt(el: HTMLElement, start: number, end: number): Range | null {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  let seen = 0;
  let begun = false;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const length = node.textContent?.length ?? 0;
    if (!begun && start < seen + length) {
      range.setStart(node, start - seen);
      begun = true;
    }
    if (begun && end <= seen + length) {
      range.setEnd(node, end - seen);
      return range;
    }
    seen += length;
  }
  return null;
}

/** The sentence to light: the given span, else the first sentence that holds a query word. */
function sentenceOf(text: string, target: FocusTarget): [number, number] | null {
  if (target.span && target.span[1] <= text.length) return target.span;
  let start = 0;
  for (const part of text.split(/(?<=[.!?])\s+|\n+/)) {
    const at = text.indexOf(part, start);
    if (target.words.some((w) => part.toLowerCase().includes(w))) return [at, at + part.length];
    start = at + part.length;
  }
  return null;
}

/** Scan the sentence in word by word, hold it, then dim it away. Returns a way to stop early. */
export function lightSentence(el: HTMLElement, target: FocusTarget): () => void {
  const span = canHighlight() && !el.matches("[role=row]") ? sentenceOf(el.textContent ?? "", target) : null;
  if (!span) return () => {};
  const [from, to] = span;
  const words = [...(el.textContent ?? "").slice(from, to).matchAll(/\S+/g)].map((m) => from + m.index + m[0].length);
  const timers: number[] = [];
  let frameId = 0;
  const set = (name: string, upTo: number) => {
    const range = rangeAt(el, from, upTo);
    if (range) CSS.highlights.set(name, new Highlight(range));
  };
  const clear = () => {
    timers.forEach(clearTimeout);
    cancelAnimationFrame(frameId);
    CSS.highlights.delete("focus-live");
    CSS.highlights.delete("focus-dim");
  };
  const hold = () => {
    set("focus-live", to);
    timers.push(window.setTimeout(() => { CSS.highlights.delete("focus-live"); set("focus-dim", to); timers.push(window.setTimeout(clear, DIM_MS)); }, HOLD_MS));
  };
  if (still() || words.length < 2) hold();
  else {
    const began = performance.now();
    const frame = (now: number) => {
      const shown = Math.ceil(Math.min((now - began) / SCAN_MS, 1) * words.length);
      set("focus-live", words[shown - 1]);
      if (shown < words.length) frameId = requestAnimationFrame(frame);
      else hold();
    };
    frameId = requestAnimationFrame(frame);
  }
  return clear;
}

/** Show a target: wait for it, scroll to it, lock on, light the sentence. Returns a cleanup. */
export function showMe(target: FocusTarget): () => void {
  const abort = new AbortController();
  const undo: (() => void)[] = [];
  void whenShown(target.kind, target.id, abort.signal).then((el) => {
    if (!el || abort.signal.aborted) return;
    el.scrollIntoView({ block: "center", behavior: still() ? "auto" : "smooth" });
    const timer = window.setTimeout(() => {
      undo.push(lockOn(el), lightSentence(el, target));
    }, still() ? 0 : SETTLE_MS);
    undo.push(() => clearTimeout(timer));
  });
  return () => {
    abort.abort();
    undo.forEach((fn) => fn());
  };
}
