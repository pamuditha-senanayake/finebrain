export function money(minor: number, currency: string, opts: { compact?: boolean } = {}) {
  const value = minor / 100;
  if (opts.compact && Math.abs(value) >= 1000) {
    return `${currency} ${new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value)}`;
  }
  return `${currency} ${new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(value)}`;
}

export function pct(x: number, digits = 0) {
  return `${(x * 100).toFixed(digits)}%`;
}

export function num(x: number) {
  return new Intl.NumberFormat("en").format(x);
}

export function usd(x: number) {
  return `$${x < 1 ? x.toFixed(3) : x.toFixed(2)}`;
}

export function relTime(iso: string, now: number = Date.now()) {
  const diff = Date.parse(iso) - now;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 60_000) return rtf.format(Math.round(diff / 1000), "second");
  if (abs < 3_600_000) return rtf.format(Math.round(diff / 60_000), "minute");
  if (abs < 86_400_000) return rtf.format(Math.round(diff / 3_600_000), "hour");
  if (abs < 30 * 86_400_000) return rtf.format(Math.round(diff / 86_400_000), "day");
  return rtf.format(Math.round(diff / (30 * 86_400_000)), "month");
}

export function date(iso: string | null, tz?: string) {
  if (!iso) return "open";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: tz }).format(new Date(iso));
}

export function dateTime(iso: string, tz?: string) {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: tz }).format(new Date(iso));
}

export function duration(ms: number) {
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.round(ms / 60_000)} min`;
}

export function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

/** Black or white text, whichever reads better on the given background colour (WCAG relative luminance). */
export function textOn(hex: string) {
  const n = parseInt(hex.replace("#", ""), 16);
  const lin = (c: number) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  const l = 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
  return (l + 0.05) / 0.05 > 1.05 / (l + 0.05) ? "#0b1020" : "#ffffff";
}
