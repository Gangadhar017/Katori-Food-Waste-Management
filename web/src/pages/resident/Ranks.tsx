// The hostel board: who helps the kitchen most, and what the resident's own notices have saved.

import { Loading, Problem } from "../../components/ui";
import type { Leaderboard, MySummary } from "../../lib/api";
import { num } from "../../lib/format";
import { useApi } from "../../lib/session";

const REASON: Record<string, string> = { skip: "Skipped in time", rating: "Rated a meal", game: "Played", streak: "Week-long streak" };

function eventText(reason: string, ref: string): string {
  const [day, what] = ref.split(":");
  const date = day?.slice(5).split("-").reverse().join("/");
  if (reason === "game") return `${REASON.game} ${what === "bin-it" ? "Bin It" : "Just Enough"} · ${date}`;
  if (reason === "streak") return `${REASON.streak} · ${date}`;
  return `${REASON[reason] ?? reason}: ${what} · ${date}`;
}

export function Ranks() {
  const board = useApi<Leaderboard>("/api/leaderboard");
  const mine = useApi<MySummary>("/api/me/summary");

  if (board.error && !board.data) return <Problem message={board.error} retry={board.reload} />;
  if (!board.data || !mine.data) return <Loading lines={3} />;

  return (
    <div className="stack">
      <section className="tray">
        <div className="tray-head">
          <h2>What your notices did</h2>
        </div>
        <div className="line-facts" style={{ borderTop: 0, marginTop: 10 }}>
          <div>
            <span className="label">Meals skipped in time</span>
            <span className="figure">{mine.data.notices}</span>
          </div>
          <div>
            <span className="label">Food not cooked</span>
            <span className="figure">{mine.data.plates_saved_kg}<span className="unit">kg</span></span>
          </div>
          <div>
            <span className="label">Your rank</span>
            <span className="figure">#{mine.data.rank}</span>
          </div>
        </div>
        <p className="tray-note">Skip in time: 5 points (twice a day). Rate a meal: 2. A game: up to 20, three scored games a day.</p>
      </section>

      <div className="day-head">
        <h2>Hostel board</h2>
        <span className="label">{num(board.data.residents)} residents</span>
      </div>
      <section className="tray">
        {board.data.rows.map((row) => (
          <div className={`rank-row ${row.me ? "me" : ""} ${row.rank <= 3 ? "top" : ""}`} key={`${row.rank}-${row.name}`}>
            <span className="pos">{String(row.rank).padStart(2, "0")}</span>
            <span>
              <b style={{ fontWeight: row.me ? 720 : 560 }}>{row.name}</b>
              {row.me && <span className="tag copper" style={{ marginLeft: 8 }}>You</span>}
              <span className="label" style={{ display: "block", marginTop: 2 }}>
                {row.block} block · {row.streak} day streak
              </span>
            </span>
            <span className="figure" style={{ fontSize: 18 }}>{num(row.points)}</span>
            <span className="label">pts</span>
          </div>
        ))}
      </section>

      <div className="day-head">
        <h2>Your last points</h2>
      </div>
      <section className="tray">
        {mine.data.events.length === 0 && <p className="empty">Nothing yet. Skip a meal you will miss, or rate one you ate.</p>}
        {mine.data.events.map((event) => (
          <div className="rank-row" key={`${event.reason}-${event.ref}`} style={{ gridTemplateColumns: "1fr auto" }}>
            <span style={{ fontSize: 14 }}>{eventText(event.reason, event.ref)}</span>
            <span className="mono">+{event.points}</span>
          </div>
        ))}
      </section>
    </div>
  );
}
