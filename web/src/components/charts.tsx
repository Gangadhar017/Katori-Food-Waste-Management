// Charts, drawn as plain SVG. One axis each, thin marks, hairline grid, a hover layer,
// and a table twin for every plotted chart.

import { useState, type ReactNode } from "react";

import { axis, num } from "../lib/format";

interface Tip {
  x: number; // percent of chart width
  y: number; // percent of chart height
  body: ReactNode;
}

function Tooltip({ tip }: { tip: Tip | null }) {
  if (!tip) return null;
  return (
    <div className="tip" style={{ left: `${Math.min(Math.max(tip.x, 13), 87)}%`, top: `${tip.y}%` }}>
      {tip.body}
    </div>
  );
}

export function Legend({ items }: { items: { name: string; color: string; shape?: "line" | "band" }[] }) {
  return (
    <div className="legend">
      {items.map((item) => (
        <span key={item.name}>
          <i className={item.shape} style={{ background: item.color }} />
          {item.name}
        </span>
      ))}
    </div>
  );
}

/** Chart or table: the same numbers either way. */
export function ChartSwitch({ chart, table, filters }: { chart: ReactNode; table: ReactNode; filters?: ReactNode }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="spread no-print" style={{ flexWrap: "wrap" }}>
        <div>{filters}</div>
        <div className="seg" role="group" aria-label="View">
          <button aria-pressed={view === "chart"} onClick={() => setView("chart")}>Chart</button>
          <button aria-pressed={view === "table"} onClick={() => setView("table")}>Table</button>
        </div>
      </div>
      {view === "chart" ? chart : table}
    </div>
  );
}

// ---------- stacked columns ----------

export interface Column {
  key: string;
  label: string; // tooltip heading
  tick: string; // x-axis label
  values: number[];
  notes?: string[];
  /** Draw a small dot under the column (a week with a holiday, for example). */
  flag?: boolean;
}

export function StackedColumns({
  columns,
  series,
  unit,
  divider,
  height = 290,
}: {
  columns: Column[];
  series: { name: string; color: string }[];
  unit: string;
  /** Draw a marked boundary before this column index. */
  divider?: { index: number; label: string };
  height?: number;
}) {
  const [tip, setTip] = useState<Tip | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const width = 780;
  const pad = { left: 46, right: 10, top: 28, bottom: 30 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const totals = columns.map((c) => c.values.reduce((a, b) => a + b, 0));
  const { top, ticks } = axis(Math.max(...totals, 1));
  const band = plotW / Math.max(columns.length, 1);
  const barW = Math.min(24, band * 0.64);
  const y = (value: number) => pad.top + plotH - (value / top) * plotH;
  const everyNth = Math.max(1, Math.ceil(columns.length / 9));

  return (
    <div className="chart" onMouseLeave={() => { setTip(null); setActive(null); }}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Stacked columns of ${series.map((s) => s.name).join(", ")} in ${unit}`}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line className={tick === 0 ? "baseline" : "gridline"} x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} />
            <text x={pad.left - 8} y={y(tick) + 3.5} textAnchor="end">{num(tick)}</text>
          </g>
        ))}
        <text x={pad.left - 8} y={12} textAnchor="end">{unit}</text>
        {divider && divider.index > 0 && divider.index < columns.length && (
          <g>
            <line x1={pad.left + band * divider.index} x2={pad.left + band * divider.index} y1={pad.top - 12} y2={pad.top + plotH} stroke="var(--copper)" strokeWidth="1" />
            <text x={pad.left + band * divider.index + 6} y={pad.top - 4} className="mark-label">{divider.label}</text>
          </g>
        )}
        {columns.map((column, index) => {
          const x = pad.left + band * index + (band - barW) / 2;
          let base = 0;
          const lastFilled = column.values.reduce((last, value, i) => (value > 0 ? i : last), -1);
          return (
            <g key={column.key} opacity={active === null || active === index ? 1 : 0.5}>
              {column.values.map((value, seriesIndex) => {
                if (value <= 0) return null;
                const y1 = y(base + value);
                const y0 = y(base);
                base += value;
                // 2px surface gap between segments; rounded cap only on the top segment.
                const h = Math.max(y0 - y1 - (seriesIndex === lastFilled ? 0 : 2), 1);
                const yTop = y0 - h;
                const r = seriesIndex === lastFilled ? Math.min(4, h, barW / 2) : 0;
                const d = `M${x},${yTop + h}V${yTop + r}a${r},${r} 0 0 1 ${r},${-r}H${x + barW - r}a${r},${r} 0 0 1 ${r},${r}V${yTop + h}Z`;
                return <path key={seriesIndex} d={d} fill={series[seriesIndex].color} />;
              })}
              {column.flag && <circle cx={x + barW / 2} cy={pad.top + plotH + 21} r="2.5" fill="var(--ink-3)" />}
              {index % everyNth === 0 && (
                <text x={x + barW / 2} y={pad.top + plotH + 15} textAnchor="middle">{column.tick}</text>
              )}
              <rect
                className="hit"
                x={pad.left + band * index}
                y={pad.top}
                width={band}
                height={plotH}
                tabIndex={0}
                aria-label={`${column.label}: ${num(totals[index], 1)} ${unit}`}
                onFocus={() => setActive(index)}
                onMouseEnter={() => {
                  setActive(index);
                  setTip({
                    x: ((x + barW / 2) / width) * 100,
                    y: (y(totals[index]) / height) * 100,
                    body: (
                      <>
                        <b>{column.label}</b>
                        {series.map((s, i) => (
                          <div className="tip-row" key={s.name}>
                            <span><i style={{ background: s.color }} />{s.name}</span>
                            <span className="mono">{num(column.values[i], 1)} {unit}</span>
                          </div>
                        ))}
                        <div className="tip-row"><span>Total</span><span className="mono">{num(totals[index], 1)} {unit}</span></div>
                        {column.notes?.map((note) => <div key={note} style={{ opacity: 0.8 }}>{note}</div>)}
                      </>
                    ),
                  });
                }}
              />
            </g>
          );
        })}
      </svg>
      <Tooltip tip={tip} />
    </div>
  );
}

// ---------- forecast against actual ----------

export interface ForecastDot {
  key: string;
  label: string;
  dayTick: string | null; // set on the first sitting of a day
  forecast: number | null;
  low: number | null;
  high: number | null;
  actual: number | null;
  note?: string;
}

export function ForecastChart({ points, ceiling, splitAt, height = 310 }: { points: ForecastDot[]; ceiling: number; splitAt: number; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const width = 900;
  const pad = { left: 44, right: 14, top: 26, bottom: 30 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const peak = Math.max(...points.map((p) => Math.max(p.high ?? 0, p.actual ?? 0, p.forecast ?? 0)), 1);
  const { top, ticks } = axis(Math.min(peak * 1.05, Math.max(ceiling, peak)));
  const step = plotW / Math.max(points.length - 1, 1);
  const x = (index: number) => pad.left + index * step;
  const y = (value: number) => pad.top + plotH - (Math.min(value, top) / top) * plotH;

  const path = (pick: (p: ForecastDot) => number | null) => {
    let d = "";
    let pen = false;
    points.forEach((p, i) => {
      const value = pick(p);
      if (value === null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(value).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const banded = points.map((p, i) => ({ p, i })).filter(({ p }) => p.low !== null && p.high !== null);
  const band = banded.length
    ? `M${banded.map(({ p, i }) => `${x(i).toFixed(1)},${y(p.high!).toFixed(1)}`).join("L")}L${banded.reverse().map(({ p, i }) => `${x(i).toFixed(1)},${y(p.low!).toFixed(1)}`).join("L")}Z`
    : "";
  const dayTicks = points.map((p, i) => ({ p, i })).filter(({ p }) => p.dayTick);
  const everyNth = Math.max(1, Math.ceil(dayTicks.length / 10));
  const lastActual = points.reduce((last, p, i) => (p.actual !== null ? i : last), -1);
  const shown = hover !== null ? points[hover] : null;

  return (
    <div
      className="chart"
      onMouseLeave={() => setHover(null)}
      onMouseMove={(event) => {
        const box = event.currentTarget.getBoundingClientRect();
        const svgX = ((event.clientX - box.left) / box.width) * width;
        const index = Math.round((svgX - pad.left) / step);
        setHover(index >= 0 && index < points.length ? index : null);
      }}
    >
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Forecast head count against residents actually served, by sitting">
        {splitAt > 0 && splitAt < points.length && (
          <g>
            <rect x={x(splitAt) - step / 2} y={pad.top} width={width - pad.right - x(splitAt) + step / 2} height={plotH} fill="var(--well)" opacity="0.55" />
            <text x={x(splitAt) - step / 2 + 6} y={pad.top - 8} className="mark-label">Still to come</text>
          </g>
        )}
        {ticks.map((tick) => (
          <g key={tick}>
            <line className={tick === 0 ? "baseline" : "gridline"} x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} />
            <text x={pad.left - 8} y={y(tick) + 3.5} textAnchor="end">{num(tick)}</text>
          </g>
        ))}
        <text x={pad.left - 8} y={12} textAnchor="end">residents</text>
        {dayTicks.map(({ p, i }, n) =>
          n % everyNth === 0 ? (
            <text key={p.key} x={x(i)} y={pad.top + plotH + 16} textAnchor="start">{p.dayTick}</text>
          ) : null,
        )}
        {band && <path d={band} fill="var(--s1)" opacity="0.13" />}
        <path d={path((p) => p.forecast)} fill="none" stroke="var(--s1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <path d={path((p) => p.actual)} fill="none" stroke="var(--s2)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {lastActual >= 0 && <circle cx={x(lastActual)} cy={y(points[lastActual].actual!)} r="4.5" fill="var(--s2)" stroke="var(--surface)" strokeWidth="2" />}
        {shown && hover !== null && (
          <g>
            <line className="hover-rule" x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + plotH} />
            {shown.forecast !== null && <circle cx={x(hover)} cy={y(shown.forecast)} r="4.5" fill="var(--s1)" stroke="var(--surface)" strokeWidth="2" />}
            {shown.actual !== null && <circle cx={x(hover)} cy={y(shown.actual)} r="4.5" fill="var(--s2)" stroke="var(--surface)" strokeWidth="2" />}
          </g>
        )}
      </svg>
      {shown && hover !== null && (
        <Tooltip
          tip={{
            x: (x(hover) / width) * 100,
            y: (y(Math.max(shown.high ?? 0, shown.actual ?? 0, shown.forecast ?? 0)) / height) * 100,
            body: (
              <>
                <b>{shown.label}</b>
                {shown.forecast !== null && (
                  <div className="tip-row"><span><i style={{ background: "var(--s1)" }} />Forecast</span><span className="mono">{num(shown.forecast)}{shown.low !== null && ` (${num(shown.low)}–${num(shown.high)})`}</span></div>
                )}
                {shown.actual !== null && (
                  <div className="tip-row"><span><i style={{ background: "var(--s2)" }} />Served</span><span className="mono">{num(shown.actual)}</span></div>
                )}
                {shown.actual !== null && shown.forecast !== null && (
                  <div className="tip-row"><span>Off by</span><span className="mono">{num(Math.abs(shown.actual - shown.forecast))}</span></div>
                )}
                {shown.note && <div style={{ opacity: 0.8 }}>{shown.note}</div>}
              </>
            ),
          }}
        />
      )}
    </div>
  );
}

// ---------- bars in rows ----------

export interface BarRow {
  key: string;
  label: ReactNode;
  value: number;
  text: string;
  title?: string;
  tone?: "steel" | "muted";
}

export function BarList({ rows, max, wide }: { rows: BarRow[]; max?: number; wide?: boolean }) {
  const top = max ?? Math.max(...rows.map((r) => r.value), 1e-9);
  return (
    <div className={wide ? "bars wide" : "bars"}>
      {rows.map((row) => (
        <div className="bar-row" key={row.key} title={row.title}>
          <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.label}</span>
          <div className="bar-track">
            <div className={`bar-fill ${row.tone ?? ""}`} style={{ width: `${Math.min((row.value / top) * 100, 100)}%` }} />
          </div>
          <span className="mono" style={{ textAlign: "right" }}>{row.text}</span>
        </div>
      ))}
    </div>
  );
}

// ---------- heatmap ----------

export function Heatmap({
  rows,
  columns,
  value,
  unit,
}: {
  rows: { key: string; label: string }[];
  columns: string[];
  value: (row: string, column: number) => number | null;
  unit: string;
}) {
  const all = rows.flatMap((row) => columns.map((_, c) => value(row.key, c))).filter((v): v is number => v !== null);
  const low = Math.min(...all);
  const high = Math.max(...all);
  const level = (v: number | null) => (v === null ? 0 : high === low ? 3 : 1 + Math.min(4, Math.floor(((v - low) / (high - low)) * 5)));
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="heat" role="table" aria-label={`${unit} by meal and weekday`}>
        <span />
        {columns.map((column) => (
          <span className="axis top" key={column}>{column}</span>
        ))}
        {rows.map((row) => (
          <div key={row.key} style={{ display: "contents" }} role="row">
            <span className="axis">{row.label}</span>
            {columns.map((column, c) => {
              const v = value(row.key, c);
              return (
                <span className={`cell h${level(v)}`} key={column} role="cell" title={`${row.label}, ${column}: ${v === null ? "no data" : `${num(v)} ${unit}`}`}>
                  {v === null ? "" : num(v)}
                </span>
              );
            })}
          </div>
        ))}
      </div>
      <div className="heat-key">
        <span>{num(low)}</span>
        {[1, 2, 3, 4, 5].map((step) => (
          <i className={`h${step}`} key={step} />
        ))}
        <span>{num(high)} {unit}</span>
      </div>
    </div>
  );
}

// ---------- the bowl ----------

/** A katori seen from the side, filled to a share of its depth. */
export function Bowl({ share, value, caption, tone = "copper" }: { share: number; value: string; caption: string; tone?: "copper" | "good" }) {
  const filled = Math.min(Math.max(share, 0), 1);
  const id = `bowl-${caption.replace(/\W+/g, "-")}`;
  return (
    <div className="bowl">
      <svg viewBox="0 0 140 84" role="img" aria-label={`${caption}: ${value}`}>
        <defs>
          <clipPath id={id}>
            <rect x="0" y={74 - filled * 56} width="140" height="84" />
          </clipPath>
        </defs>
        <path d="M14 18a56 56 0 0 0 112 0z" fill="var(--well)" />
        <path d="M14 18a56 56 0 0 0 112 0z" fill={tone === "good" ? "var(--good)" : "var(--copper)"} clipPath={`url(#${id})`} />
        <path d="M14 18a56 56 0 0 0 112 0" fill="none" stroke="var(--line-strong)" strokeWidth="2" />
        <path d="M6 15h128" stroke="var(--ink)" strokeWidth="3.5" strokeLinecap="round" />
        <path d="M52 78h36" stroke="var(--line-strong)" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <span className="figure">{value}</span>
      <span className="label" style={{ textAlign: "center" }}>{caption}</span>
    </div>
  );
}
