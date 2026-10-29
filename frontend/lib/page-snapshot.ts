"use client";

// What the person sees right now, as plain text for Lisena. It runs only when a question is sent, reads the
// rendered page (so it works on every screen without per-page code), and keeps it short: selected text first, then any
// open dialog, then the main area, with blank and repeated lines dropped. Mark parts to skip with data-ask-ignore.

// Config
const MOST_CHARS = 4000;
const MOST_LINES = 160;
const APP_NAME = " · Company Brain";

export type PageSnapshot = { path: string; title: string; snapshot: string };

/** The rendered text of an element (what is visible), minus anything marked data-ask-ignore. */
function visibleText(el: Element | null): string {
  if (!el) return "";
  let text = (el as HTMLElement).innerText ?? "";
  for (const node of el.querySelectorAll("[data-ask-ignore]")) {
    const part = (node as HTMLElement).innerText;
    if (part) text = text.replace(part, "");
  }
  return text;
}

function tidy(text: string): string[] {
  const lines: string[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.replace(/\s+/g, " ").trim();
    if (line && line !== lines[lines.length - 1]) lines.push(line);
  }
  return lines;
}

/** The current page, ready to send with a question. */
export function snapshotPage(): PageSnapshot {
  const selected = window.getSelection()?.toString().trim() ?? "";
  const dialogs = [...document.querySelectorAll("[role=dialog]:not([data-ask-ignore])")].map(visibleText).join("\n");
  const main = visibleText(document.querySelector("main"));
  const parts = [selected && `Selected: ${selected}`, dialogs && `Open panel:\n${dialogs}`, main].filter(Boolean).join("\n");
  const lines = tidy(parts).slice(0, MOST_LINES);
  let snapshot = lines.join("\n");
  if (snapshot.length > MOST_CHARS) snapshot = `${snapshot.slice(0, MOST_CHARS)}…`;
  return { path: location.pathname + location.search, title: document.title.replace(APP_NAME, "").trim(), snapshot };
}
