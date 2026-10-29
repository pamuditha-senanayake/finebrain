// logo.tsx: the FineBrain mark (a crowned face drawn in one line weight) and the "Fine**Brain**" wordmark, from the brand card.
// The mark takes the text colour, so it reads in light and dark. Used by: components/shell/sidebar.tsx, app-shell.tsx, features/home.tsx.
import { cn } from "@/lib/utils";

// Traced from the brand card; swap in the designer's master SVG path here when it arrives.
const MARK_PATH = "M45.6,123.8 L73.2,123.8 L71.2,119.0 L69.2,117.5 L48.8,117.5Z M99.0,77.4 L75.5,77.4 L62.4,84.5 L62.4,102.9 L58.9,104.9 L51.3,101.4 L49.4,107.5 L58.5,112.7 L68.9,108.0 L69.3,106.3 L69.5,88.9 L69.5,87.1 L77.1,84.1 L99.0,84.1Z M118.2,26.1 L96.1,35.5 L96.1,13.0 L76.4,23.6 L58.8,0.0 L41.6,23.8 L21.5,12.8 L21.5,35.4 L0.0,26.2 L18.2,65.8 L18.2,165.5 L25.1,165.5 L25.1,121.0 L47.1,145.1 L66.0,145.0 L66.0,138.3 L49.8,138.3 L25.3,109.6 L25.3,84.2 L41.5,84.2 L50.3,88.4 L53.6,83.9 L43.5,77.1 L25.4,77.1 L25.4,66.5 L59.5,52.1 L98.3,68.2Z M14.2,40.5 L32.0,48.2 L59.0,37.2 L85.2,48.2 L104.1,40.7 L94.8,59.3 L59.2,44.7 L23.2,59.3Z M88.9,25.4 L88.9,40.3 L85.2,40.3 L73.0,35.4 L83.1,28.1Z M29.1,25.2 L45.0,35.4 L33.3,40.1 L29.1,40.1Z M58.8,12.0 L70.1,27.4 L64.6,31.6 L59.0,29.9 L53.8,31.8 L47.9,27.7Z";

/** The mark alone. Give it a height; the width follows (it is a little taller than wide). */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 118.2 165.5" className={cn("h-7 w-auto shrink-0", className)} fill="currentColor" aria-hidden>
      <path fillRule="evenodd" d={MARK_PATH} />
    </svg>
  );
}

/** "Fine" light and "Brain" bold, as on the brand card. */
export function BrandName({ className }: { className?: string }) {
  return (
    <span className={cn("tracking-tight", className)}>
      <span className="font-light">Fine</span>
      <span className="font-bold">Brain</span>
    </span>
  );
}
