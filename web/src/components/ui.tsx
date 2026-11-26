// Small building blocks shared by every screen.

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import type { DishRef, SittingState } from "../lib/api";

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="5" fill="var(--ink)" />
      <path d="M5 13h22a11 11 0 0 1-22 0z" fill="var(--copper)" />
      <path d="M4 12.2h24" stroke="var(--surface)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Brand({ sub }: { sub?: string }) {
  return (
    <span className="brand">
      <Logo />
      <span>
        <span className="brand-name" style={{ display: "block" }}>
          Katori
        </span>
        {sub && <span className="brand-sub" style={{ display: "block" }}>{sub}</span>}
      </span>
    </span>
  );
}

const ICONS: Record<string, ReactNode> = {
  plate: (<><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /></>),
  week: (<><rect x="3.5" y="5" width="17" height="15" rx="1.5" /><path d="M3.5 10h17M9 5v15M15 5v15" /></>),
  line: (<><circle cx="6" cy="8" r="2.2" /><circle cx="12" cy="8" r="2.2" /><circle cx="18" cy="8" r="2.2" /><path d="M3 18c0-2.5 1.3-4 3-4s3 1.5 3 4M9 18c0-2.5 1.3-4 3-4s3 1.5 3 4M15 18c0-2.5 1.3-4 3-4s3 1.5 3 4" /></>),
  trophy: (<><path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H4.5c0 3 1.5 4.5 3.5 4.5M16 6h3.5c0 3-1.5 4.5-3.5 4.5M12 13v4M8.5 20h7M10 17h4" /></>),
  sheet: (<><rect x="5" y="4" width="14" height="17" rx="1.5" /><path d="M9 4V2.8h6V4M8.5 10h7M8.5 13.5h7M8.5 17h4" /></>),
  scale: (<><path d="M4 20h16l-1.5-9h-13zM8 11V8a4 4 0 0 1 8 0v3" /><path d="M12 14.5l2-2" /></>),
  bell: (<><path d="M5 17h14M6.5 17a5.5 5.5 0 0 1 11 0M12 8.5V6.5M10.5 6.5h3" /><path d="M3.5 20h17" /></>),
  gauge: (<><path d="M4 17a8 8 0 1 1 16 0" /><path d="M12 17l4-5" /><circle cx="12" cy="17" r="1.2" /></>),
  trend: (<><path d="M3.5 19.5h17M4.5 15l4.5-4.5 3.5 3L19.5 6" /><path d="M15.5 6h4v4" /></>),
  bin: (<><path d="M5 7h14M9.5 7V4.8h5V7M6.5 7l1 13h9l1-13M10 10.5v6M14 10.5v6" /></>),
  table: (<><rect x="3.5" y="4.5" width="17" height="15" rx="1.5" /><path d="M3.5 9.5h17M3.5 14.5h17M9.5 4.5v15" /></>),
  nodes: (<><circle cx="6" cy="6.5" r="2.3" /><circle cx="18" cy="6.5" r="2.3" /><circle cx="12" cy="17.5" r="2.3" /><path d="M7.4 8.4l3.4 7.1M16.6 8.4l-3.4 7.1M8.3 6.5h7.4" /></>),
  sun: (<><circle cx="12" cy="12" r="3.6" /><path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M6 6l1.4 1.4M16.6 16.6L18 18M6 18l1.4-1.4M16.6 7.4L18 6" /></>),
  moon: <path d="M19 14.5A7.5 7.5 0 0 1 9.5 5a7.5 7.5 0 1 0 9.5 9.5z" />,
  exit: (<><path d="M14 4.5h4.5v15H14M10.5 8.5L14 12l-3.5 3.5M14 12H4.5" /></>),
  back: <path d="M14.5 5.5L8 12l6.5 6.5" />,
  play: <path d="M8 5.5v13l10.5-6.5z" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
};

export function Icon({ name, size = 18 }: { name: keyof typeof ICONS | string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[name]}
    </svg>
  );
}

export function VegMark({ veg }: { veg: boolean }) {
  return <span className={veg ? "veg-mark" : "veg-mark non"} role="img" aria-label={veg ? "Vegetarian" : "Non-vegetarian"} />;
}

export function Dishes({ dishes }: { dishes: DishRef[] }) {
  return (
    <div className="dishes">
      {dishes.map((dish) => (
        <span className="dish" key={dish.id}>
          <VegMark veg={dish.veg} />
          {dish.name}
        </span>
      ))}
    </div>
  );
}

const STATE_TAG: Record<SittingState, [string, string]> = {
  open: ["Notice open", "tag"],
  cooking: ["Cooking", "tag warn"],
  serving: ["Serving now", "tag copper"],
  done: ["Served", "tag"],
};

export function StateTag({ state }: { state: SittingState }) {
  const [text, className] = STATE_TAG[state];
  return <span className={className}>{text}</span>;
}

export function PageHead({ eyebrow, title, sub, children }: { eyebrow: string; title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <>
      <header className="page-head">
        <div>
          <p className="label">{eyebrow}</p>
          <h1 className="title">{title}</h1>
          {sub && <p className="subtitle" style={{ marginTop: 6 }}>{sub}</p>}
        </div>
        {children && <div className="row no-print">{children}</div>}
      </header>
      <div className="rule" />
    </>
  );
}

export function Readout({
  label,
  value,
  unit,
  children,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  children?: ReactNode;
}) {
  return (
    <div className="readout">
      <span className="label">{label}</span>
      <span>
        <span className="figure">{value}</span>
        {unit && <span className="unit">{unit}</span>}
      </span>
      {children && <span className="delta">{children}</span>}
    </div>
  );
}

/** "12% less than the four weeks before" with the right colour for whether less is good. */
export function Change({ now, before, lowerIsBetter = true, suffix = "vs the 4 weeks before" }: { now?: number | null; before?: number | null; lowerIsBetter?: boolean; suffix?: string }) {
  if (now === null || now === undefined || !before) return <span>{suffix.startsWith("vs") ? "no earlier period to compare" : suffix}</span>;
  const change = ((now - before) / before) * 100;
  if (Math.abs(change) < 0.5) return <span>level {suffix}</span>;
  const better = change < 0 === lowerIsBetter;
  return (
    <>
      <span className={better ? "good" : "bad"}>
        {change < 0 ? "▼" : "▲"} {Math.abs(change).toFixed(0)}% {better ? "better" : "worse"}
      </span>
      <span>{suffix}</span>
    </>
  );
}

export function Loading({ lines = 2 }: { lines?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, index) => (
        <div className="skeleton" key={index} />
      ))}
    </div>
  );
}

export function Problem({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="notice bad" role="alert">
      <div style={{ flex: 1 }}>
        <b>That did not load.</b> {message}
      </div>
      {retry && (
        <button className="btn ghost small" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={panel}>
        <div className="spread">
          <h2 className="title" style={{ fontSize: 20 }}>{title}</h2>
          <button className="btn ghost small" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

const ToastContext = createContext<(message: string) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef(0);
  const show = useCallback((next: string) => {
    setMessage(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMessage(null), 3200);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {message && (
        <div className="toast" role="status">
          {message}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): (message: string) => void {
  return useContext(ToastContext);
}
