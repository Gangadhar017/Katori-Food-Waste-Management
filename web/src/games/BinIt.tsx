// Bin It: forty seconds of sorting what comes off a mess tray into the right bin.

import { useCallback, useEffect, useRef, useState } from "react";

type Bin = "compost" | "recycle" | "landfill";

const ITEMS: { glyph: string; name: string; bin: Bin; why: string }[] = [
  { glyph: "🍌", name: "Banana peel", bin: "compost", why: "Peels turn into compost in about eight weeks." },
  { glyph: "🍵", name: "Used tea leaves", bin: "compost", why: "Tea leaves are one of the best things you can add to a compost pit." },
  { glyph: "🫓", name: "Leftover roti", bin: "compost", why: "Cooked food scraps go to compost or biogas, never to the dry-waste bin." },
  { glyph: "🥚", name: "Egg shells", bin: "compost", why: "Crushed shells break down and add calcium to compost." },
  { glyph: "🥕", name: "Vegetable peels", bin: "compost", why: "Kitchen peels are the bulk of a mess's wet waste, and all of it composts." },
  { glyph: "🍚", name: "Leftover rice", bin: "compost", why: "Plate leftovers are wet waste: compost or biogas." },
  { glyph: "🌼", name: "Flower garland", bin: "compost", why: "Flowers are wet waste. Take the thread out first." },
  { glyph: "🍋", name: "Squeezed lemon", bin: "compost", why: "Citrus composts fine in a mixed pit." },
  { glyph: "🍾", name: "Glass bottle", bin: "recycle", why: "Glass can be melted and remade without limit." },
  { glyph: "🥫", name: "Empty tin can", bin: "recycle", why: "Steel and aluminium cans are among the most valuable things in the dry bin." },
  { glyph: "📰", name: "Old newspaper", bin: "recycle", why: "Dry paper is recycled; it only fails when it gets wet or oily." },
  { glyph: "🧴", name: "Rinsed plastic bottle", bin: "recycle", why: "PET bottles recycle well once they are empty and rinsed." },
  { glyph: "📦", name: "Cardboard box", bin: "recycle", why: "Flatten it and keep it dry." },
  { glyph: "🥛", name: "Rinsed milk pouch", bin: "recycle", why: "Milk pouches are recyclable plastic if you rinse them." },
  { glyph: "🧃", name: "Juice carton", bin: "recycle", why: "Cartons are collected and recycled into boards and sheets." },
  { glyph: "🍟", name: "Chips packet", bin: "landfill", why: "Shiny multi-layer packets cannot be recycled in most cities." },
  { glyph: "🥡", name: "Thermocol plate", bin: "landfill", why: "Thermocol is almost never recycled. Steel plates avoid it entirely." },
  { glyph: "☕", name: "Broken ceramic cup", bin: "landfill", why: "Ceramic does not melt with glass, so it cannot go in recycling." },
  { glyph: "🖊️", name: "Dead ball pen", bin: "landfill", why: "Mixed plastic, metal and ink: not recyclable as it is." },
  { glyph: "🍬", name: "Toffee wrapper", bin: "landfill", why: "Too small and too mixed to recover." },
  { glyph: "🧻", name: "Oily paper napkin", bin: "landfill", why: "Oil ruins paper for recycling." },
];

const BINS: { bin: Bin; name: string; hint: string }[] = [
  { bin: "compost", name: "Compost", hint: "wet waste" },
  { bin: "recycle", name: "Recycle", hint: "dry, clean" },
  { bin: "landfill", name: "Landfill", hint: "the rest" },
];

function shuffled<T>(list: T[]): T[] {
  const copy = [...list];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

export function BinIt({ onFinish, seconds = 40 }: { onFinish?: (score: number) => void; seconds?: number }) {
  const [phase, setPhase] = useState<"ready" | "playing" | "over">("ready");
  const [queue, setQueue] = useState(() => shuffled(ITEMS));
  const [index, setIndex] = useState(0);
  const [score, setScore] = useState(0);
  const [streak, setStreak] = useState(0);
  const [left, setLeft] = useState(seconds);
  const [verdict, setVerdict] = useState<{ right: boolean; why: string } | null>(null);
  const [sorted, setSorted] = useState({ right: 0, wrong: 0 });
  const locked = useRef(false);
  const scoreRef = useRef(0);
  const item = queue[index % queue.length];

  const start = () => {
    setQueue(shuffled(ITEMS));
    setIndex(0);
    setScore(0);
    scoreRef.current = 0;
    setStreak(0);
    setLeft(seconds);
    setVerdict(null);
    setSorted({ right: 0, wrong: 0 });
    locked.current = false;
    setPhase("playing");
  };

  useEffect(() => {
    if (phase !== "playing") return;
    const started = performance.now();
    const timer = window.setInterval(() => {
      const remaining = seconds - (performance.now() - started) / 1000;
      if (remaining <= 0) {
        window.clearInterval(timer);
        setLeft(0);
        setPhase("over");
        onFinish?.(scoreRef.current);
      } else setLeft(remaining);
    }, 100);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, seconds]);

  const choose = useCallback(
    (bin: Bin) => {
      if (phase !== "playing" || locked.current) return;
      const right = bin === item.bin;
      locked.current = true;
      setVerdict({ right, why: item.why });
      setSorted((s) => ({ right: s.right + (right ? 1 : 0), wrong: s.wrong + (right ? 0 : 1) }));
      const gain = right ? 10 + 2 * Math.min(streak, 5) : -5;
      scoreRef.current = Math.max(0, scoreRef.current + gain);
      setScore(scoreRef.current);
      setStreak(right ? streak + 1 : 0);
      window.setTimeout(
        () => {
          setVerdict(null);
          setIndex((i) => i + 1);
          locked.current = false;
        },
        right ? 260 : 1300,
      );
    },
    [phase, item, streak],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const map: Record<string, Bin> = { "1": "compost", "2": "recycle", "3": "landfill", ArrowLeft: "compost", ArrowDown: "recycle", ArrowRight: "landfill" };
      if (map[event.key]) {
        event.preventDefault();
        choose(map[event.key]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [choose]);

  if (phase === "ready") {
    return (
      <div className="game">
        <div className="item-card">
          <span className="glyph">🍌</span>
          <b>Bin It</b>
        </div>
        <p className="muted" style={{ textAlign: "center" }}>
          Forty seconds. Send each thing from the tray to the right bin. A run of right answers scores more; a wrong one costs five.
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
          <span className="label">Time</span>
          <span className="figure">{score}</span>
          <p className="muted">
            {sorted.right} sorted right, {sorted.wrong} wrong.
          </p>
          <button className="btn block" onClick={start}>
            Play again
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="game">
      <div className="game-hud">
        <div>
          <span className="label">Score</span>
          <span className="figure">{score}</span>
        </div>
        <div>
          <span className="label">Run</span>
          <span className="figure">{streak}</span>
        </div>
        <div>
          <span className="label">Time</span>
          <span className="figure">{Math.ceil(left)}<span className="unit">s</span></span>
        </div>
      </div>
      <div className="progress" aria-hidden="true">
        <i style={{ width: `${(left / seconds) * 100}%`, transition: "width 0.1s linear" }} />
      </div>
      <div className={`item-card ${verdict ? (verdict.right ? "right" : "wrong") : ""}`} aria-live="polite">
        <span className="glyph">{item.glyph}</span>
        <b>{item.name}</b>
        {verdict && !verdict.right && <span style={{ padding: "0 14px", fontSize: 13.5 }}>{verdict.why}</span>}
      </div>
      <div className="bins">
        {BINS.map((bin, n) => (
          <button className={`bin ${bin.bin}`} key={bin.bin} onClick={() => choose(bin.bin)}>
            {bin.name}
            <small>
              {bin.hint} · {n + 1}
            </small>
          </button>
        ))}
      </div>
    </div>
  );
}
