// The screen on the dining-hall wall: who is being served, how long the line is, what is on the counter.

import { Link, useParams } from "react-router-dom";

import { VegMark } from "../components/ui";
import type { BoardView } from "../lib/api";
import { clock, dayLabel, MEAL_LABEL, num, waitText } from "../lib/format";
import { useApi, useLine, useNow } from "../lib/session";

export function Board() {
  const { slug = "" } = useParams();
  const board = useApi<BoardView>(`/api/public/${slug}/board`, 120000);
  const { snapshot, live } = useLine({ kind: "board", slug });
  const now = useNow(15000);
  const line = snapshot ?? board.data?.line ?? null;

  if (board.error && !board.data) {
    return (
      <div className="board">
        <p>This display could not reach the kitchen. {board.error}</p>
        <Link to="/" style={{ color: "#f09a6c" }}>
          Back to Katori
        </Link>
      </div>
    );
  }
  if (!board.data || !line) return <div className="board" aria-busy="true" />;

  const { service } = line;
  const counters = Array.from({ length: line.line.counters }, (_, index) => index + 1);
  const yesterday = board.data.yesterday;
  return (
    <div className="board">
      <header className="board-top">
        <div>
          <p className="label">
            {board.data.hostel} · {dayLabel(board.data.today, "long")}
          </p>
          <h1 className="display" style={{ fontSize: "clamp(26px, 4vw, 54px)", marginTop: 6, textTransform: "uppercase" }}>
            {MEAL_LABEL[service.meal]}
            <span style={{ color: "#8d9895", fontWeight: 500, fontStretch: "100%", fontSize: "0.5em", marginLeft: 14, letterSpacing: 0 }}>
              {service.phase === "open" ? `until ${clock(service.closes_at)}` : `opens ${clock(service.opens_at)}`}
            </span>
          </h1>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="figure" style={{ fontSize: "clamp(22px, 3vw, 40px)" }}>{clock(new Date(now).toISOString())}</div>
          <p className="label" style={{ marginTop: 6 }}>{live ? "Live" : "Reconnecting"}</p>
        </div>
      </header>

      <main className="board-main">
        <section className="board-panel">
          <p className="label">Now serving</p>
          <div className="serving">
            {counters.map((counter) => {
              const serving = line.line.now_serving.find((s) => s.counter === counter);
              return (
                <div className="serving-slot" key={counter}>
                  <span className="label">Counter {counter}</span>
                  <span className="figure">{serving ? serving.token : "–"}</span>
                </div>
              );
            })}
          </div>
          <p className="label" style={{ marginTop: 8 }}>Next up</p>
          <div className="next-tokens">
            {line.line.next_tokens.length ? line.line.next_tokens.map((token) => <span key={token}>{token}</span>) : <span>No one waiting</span>}
          </div>
          {service.preview && <p className="label">Demo line: a simulated crowd, shown before the counter opens</p>}
        </section>

        <section className="board-panel">
          <div className="spread" style={{ alignItems: "flex-start" }}>
            <div>
              <p className="label">In line</p>
              <div className="figure board-fig">{line.line.waiting}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <p className="label">Wait if you join now</p>
              <div className="figure board-fig" style={{ fontSize: "clamp(24px, 3.2vw, 46px)" }}>{waitText(line.line.join_wait_s)}</div>
            </div>
          </div>
          <p className="label" style={{ marginTop: 6 }}>On the counter</p>
          <div className="board-menu">
            {service.menu.map((dish) => (
              <div key={dish.id}>
                <VegMark veg={dish.veg} />
                {dish.name}
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="spread" style={{ borderTop: "1px solid #2c3436", paddingTop: 14, flexWrap: "wrap" }}>
        <p style={{ fontSize: "clamp(14px, 1.5vw, 20px)", color: "#c6cecb", maxWidth: "70ch" }}>
          {yesterday.served > 0 ? (
            <>
              Yesterday <b style={{ color: "#f09a6c" }}>{num(yesterday.plate_waste_kg)} kg</b> came back on plates. That is about {num(yesterday.plates)} full meals. Take what you will eat; come back for more.
            </>
          ) : (
            "Take what you will eat; come back for more."
          )}
        </p>
        <Link to="/" className="label" style={{ color: "#8d9895" }}>
          Katori
        </Link>
      </footer>
    </div>
  );
}
