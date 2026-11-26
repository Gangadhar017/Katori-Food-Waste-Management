// Just Enough: pour a portion by eye. Hold to pour, let go when you think the bowl holds the target.

import { useEffect, useRef, useState } from "react";

const ROUNDS = [
  { dish: "steamed rice", grams: 180, bowl: 300, rate: 85 },
  { dish: "dal tadka", grams: 150, bowl: 400, rate: 115 },
  { dish: "aloo gobi", grams: 130, bowl: 260, rate: 135 },
  { dish: "kheer", grams: 120, bowl: 350, rate: 165 },
  { dish: "rajma", grams: 170, bowl: 280, rate: 195 },
];

interface Result {
  poured: number;
  target: number;
  points: number;
}

function roundPoints(poured: number, target: number): number {
  const error = Math.abs(poured - target) / target;
  return Math.round(100 * Math.max(0, 1 - 2.5 * error));
}

export function JustEnough({ onFinish }: { onFinish?: (score: number) => void }) {
  const [phase, setPhase] = useState<"ready" | "playing" | "over">("ready");
  const [round, setRound] = useState(0);
  const [grams, setGrams] = useState(0);
  const [results, setResults] = useState<Result[]>([]);
  const [shown, setShown] = useState<Result | null>(null);
  const pouring = useRef(false);
  const frame = useRef(0);
  const poured = useRef(0);
  const current = ROUNDS[Math.min(round, ROUNDS.length - 1)];
  const total = results.reduce((sum, r) => sum + r.points, 0);

  const start = () => {
    setRound(0);
    setResults([]);
    setShown(null);
    setGrams(0);
    poured.current = 0;
    setPhase("playing");
  };

  const stop = () => {
    if (!pouring.current) return;
    pouring.current = false;
    cancelAnimationFrame(frame.current);
    const result = { poured: Math.round(poured.current), target: current.grams, points: roundPoints(poured.current, current.grams) };
    setShown(result);
    const all = [...results, result];
    setResults(all);
    window.setTimeout(() => {
      setShown(null);
      setGrams(0);
      poured.current = 0;
      if (all.length >= ROUNDS.length) {
        setPhase("over");
        onFinish?.(all.reduce((sum, r) => sum + r.points, 0));
      } else setRound(all.length);
    }, 1700);
  };

  const pour = () => {
    if (phase !== "playing" || shown || pouring.current) return;
    pouring.current = true;
    let last = performance.now();
    const held = last;
    const tick = (now: number) => {
      if (!pouring.current) return;
      // The ladle speeds up the longer it is tipped.
      const speed = current.rate * (1 + 0.5 * ((now - held) / 1000));
      poured.current = Math.min(poured.current + (speed * (now - last)) / 1000, current.bowl);
      last = now;
      setGrams(poured.current);
      if (poured.current >= current.bowl) stop();
      else frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
  };

  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.code === "Space" && !event.repeat) {
        event.preventDefault();
        pour();
      }
    };
    const up = (event: KeyboardEvent) => event.code === "Space" && stop();
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  });

  if (phase === "ready") {
    return (
      <div className="game">
        <div className="item-card">
          <span className="glyph">🥣</span>
          <b>Just Enough</b>
        </div>
        <p className="muted" style={{ textAlign: "center" }}>
          Five bowls. Hold the button to pour and let go when you think the bowl holds the portion asked for. No scale, no line: judge it by eye.
        </p>
        <button className="btn copper block" onClick={start}>
          Start
        </button>
      </div>
    );
  }
  if (phase === "over") {
    return (
      <div className="game">
        <div className="game-over tray">
          <span className="label">Five bowls served</span>
          <span className="figure">{total}</span>
          <table className="table" style={{ maxWidth: 320 }}>
            <tbody>
              {results.map((r, i) => (
                <tr key={i}>
                  <td style={{ textTransform: "capitalize" }}>{ROUNDS[i].dish}</td>
                  <td className="num">
                    {r.poured} / {r.target} g
                  </td>
                  <td className="num">{r.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="btn block" onClick={start}>
            Play again
          </button>
        </div>
      </div>
    );
  }

  const level = Math.min(grams / current.bowl, 1);
  const off = shown ? shown.poured - shown.target : 0;
  return (
    <div className="game">
      <div className="game-hud">
        <div>
          <span className="label">Bowl</span>
          <span className="figure">{Math.min(round + 1, ROUNDS.length)}<span className="unit">of {ROUNDS.length}</span></span>
        </div>
        <div>
          <span className="label">Serve</span>
          <span className="figure">{current.grams}<span className="unit">g</span></span>
        </div>
        <div>
          <span className="label">Score</span>
          <span className="figure">{total}</span>
        </div>
      </div>
      <div className="tray pour">
        <p style={{ textAlign: "center", padding: "12px 14px 0" }}>
          Serve <b>{current.grams} g</b> of {current.dish}. This bowl holds <b>{current.bowl} g</b> to the brim.
        </p>
        <svg viewBox="0 0 240 150" role="img" aria-label="A bowl being filled">
          <defs>
            <clipPath id="pour-clip">
              <rect x="0" y={130 - level * 100} width="240" height="150" />
            </clipPath>
          </defs>
          <path d="M20 30a100 100 0 0 0 200 0z" fill="var(--well)" />
          <path d="M20 30a100 100 0 0 0 200 0z" fill="var(--copper)" clipPath="url(#pour-clip)" />
          <path d="M20 30a100 100 0 0 0 200 0" fill="none" stroke="var(--line-strong)" strokeWidth="3" />
          <path d="M8 26h224" stroke="var(--ink)" strokeWidth="5" strokeLinecap="round" />
          <path d="M92 140h56" stroke="var(--line-strong)" strokeWidth="4" strokeLinecap="round" />
        </svg>
        <div style={{ minHeight: 46, textAlign: "center", padding: "0 14px 12px" }} aria-live="polite">
          {shown ? (
            <>
              <b>
                {shown.poured} g poured: +{shown.points}
              </b>
              <div className="muted" style={{ fontSize: 13.5 }}>
                {Math.abs(off) <= shown.target * 0.05 ? "Just enough." : off > 0 ? `${off} g too much. That is what ends up in the bin.` : `${-off} g short. Someone goes back for seconds.`}
              </div>
            </>
          ) : (
            <span className="muted">Hold to pour, let go to stop.</span>
          )}
        </div>
      </div>
      <button
        className="btn copper block"
        style={{ minHeight: 56, fontSize: 16 }}
        disabled={Boolean(shown)}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          pour();
        }}
        onPointerUp={stop}
        onPointerCancel={stop}
        onContextMenu={(event) => event.preventDefault()}
      >
        Hold to pour
      </button>
    </div>
  );
}
