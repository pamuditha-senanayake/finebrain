import { en, type MessageKey } from "./en";

// English ships first. Add a catalogue with the same keys to add a locale.
const catalogues = { en } as const;
export type Locale = keyof typeof catalogues;

let current: Locale = "en";

export function setLocale(locale: Locale) {
  current = locale;
}

export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  let text: string = catalogues[current][key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
  return text;
}

export type { MessageKey };
