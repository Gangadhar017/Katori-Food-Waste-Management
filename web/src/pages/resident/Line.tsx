// The serving line: take a token, watch your place move, play while you wait.

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { Dishes, Loading, useToast } from "../../components/ui";
import { api, type LineSnapshot } from "../../lib/api";
import { clock, MEAL_LABEL, waitText } from "../../lib/format";
import { useLine } from "../../lib/session";

export function GameDoors() {
  return (
    <div className="grid two" style={{ gridTemplateColumns: "1fr 1fr", gap: 8 }}>
      <Link className="tray" to="/play/bin-it" style={{ padding: 14, textDecoration: "none", display: "grid", gap: 4 }}>
        <span style={{ fontSize: 28 }}>🍌</span>
        <b>Bin It</b>
        <span className="muted" style={{ fontSize: 12.5 }}>Sort the tray. 40 seconds.</span>
      </Link>
      <Link className="tray" to="/play/just-enough" style={{ padding: 14, textDecoration: "none", display: "grid", gap: 4 }}>
        <span style={{ fontSize: 28 }}>🥣</span>
        <b>Just Enough</b>
        <span className="muted" style={{ fontSize: 12.5 }}>Pour a portion by eye.</span>
      </Link>
    </div>
  );
}

/** Buzz and toast once when the resident's token is called. */
export function useTurnAlert(snapshot: LineSnapshot | null): void {
  const toast = useToast();
  const last = useRef<string | null>(null);
  const status = snapshot?.ticket?.status ?? null;
  const counter = snapshot?.ticket?.counter;
  useEffect(() => {
    if (status === "called" && last.current === "waiting") {
      toast(`Your turn. Go to counter ${counter}.`);
      navigator.vibrate?.([180, 90, 180]);
    }
    last.current = status;
  }, [status, counter, toast]);
}

export function Line() {
  const { snapshot, live, push } = useLine({ kind: "member" });
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  useTurnAlert(snapshot);

  if (!snapshot) return <Loading lines={2} />;
  const { service, line, ticket } = snapshot;

  const act = async (path: string) => {
    setBusy(true);
    try {
      push(await api<LineSnapshot>(path, { method: "POST" }));
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const serving = line.now_serving.map((s) => s.token).join(" · ") || "–";
  const progress = ticket && ticket.status === "waiting" ? 1 - ticket.ahead / Math.max(ticket.ahead + line.now_serving.length, Math.round(ticket.quoted_wait_s / 9), 1) : 1;

  return (
    <div className="stack">
      <div className="day-head">
        <h2>{MEAL_LABEL[service.meal]} line</h2>
        <span className="label">{live ? "Live" : "Updating"}</span>
      </div>
      {service.preview && (
        <div className="notice">
          <div>
            <b>The counter opens at {clock(service.opens_at)}.</b> Until then this is a simulated crowd, so you can try the line now.
          </div>
        </div>
      )}

      {!ticket || ticket.status === "served" ? (
        <section className="tray">
          {ticket?.status === "served" && (
            <div className="tray-note" style={{ borderTop: 0, borderBottom: "1px solid var(--line)" }}>
              <b>Token {ticket.token} served.</b> Enjoy your meal, and rate it from Today when you are done.
            </div>
          )}
          <div className="line-facts" style={{ borderTop: 0 }}>
            <div>
              <span className="label">In line</span>
              <span className="figure">{line.waiting}</span>
            </div>
            <div>
              <span className="label">Counters</span>
              <span className="figure">{line.counters}</span>
            </div>
            <div>
              <span className="label">Wait now</span>
              <span className="figure" style={{ fontSize: 17, lineHeight: 1.4 }}>{waitText(line.join_wait_s)}</span>
            </div>
          </div>
          <div className="tray-body stack" style={{ gap: 10, borderTop: "1px solid var(--line)" }}>
            <button className="btn copper block" style={{ minHeight: 50, fontSize: 16 }} disabled={busy} onClick={() => act("/api/line/join")}>
              Take a token
            </button>
            <p className="muted" style={{ fontSize: 13, textAlign: "center" }}>Sit down. Your phone tells you when to walk up.</p>
          </div>
        </section>
      ) : (
        <section className="tray">
          <div className="tray-body stack" style={{ gap: 14, paddingTop: 20 }}>
            <div className={`token ${ticket.status === "called" ? "called" : ""}`} aria-live="polite">
              <span className="label">Token</span>
              <span className="token-num">{ticket.token}</span>
              <span className="token-foot">{ticket.status === "called" ? `Counter ${ticket.counter}` : MEAL_LABEL[service.meal]}</span>
            </div>
            {ticket.status === "called" ? (
              <p style={{ textAlign: "center", fontWeight: 680, fontSize: 18 }}>Your turn. Walk up to counter {ticket.counter}.</p>
            ) : (
              <>
                <p style={{ textAlign: "center" }}>
                  <b>{ticket.ahead === 0 ? "You are next." : `${ticket.ahead} ahead of you.`}</b> <span className="muted">{ticket.ahead ? waitText(ticket.eta_s) : ""}</span>
                </p>
                <div className="progress" aria-hidden="true">
                  <i style={{ width: `${Math.max(progress, 0.04) * 100}%` }} />
                </div>
              </>
            )}
          </div>
          <div className="line-facts">
            <div>
              <span className="label">Now serving</span>
              <span className="figure" style={{ fontSize: 19 }}>{serving}</span>
            </div>
            <div>
              <span className="label">Behind you</span>
              <span className="figure">{Math.max(line.waiting - ticket.ahead - (ticket.status === "waiting" ? 1 : 0), 0)}</span>
            </div>
            <div>
              <span className="label">Waited</span>
              <span className="figure" style={{ fontSize: 19 }}>
                {Math.floor(ticket.waited_s / 60)}:{String(ticket.waited_s % 60).padStart(2, "0")}
              </span>
            </div>
          </div>
          {ticket.status === "waiting" && (
            <div className="tray-note">
              <button className="btn ghost small" disabled={busy} onClick={() => act("/api/line/leave")}>
                Give up my token
              </button>
            </div>
          )}
        </section>
      )}

      <div className="day-head">
        <h2>While you wait</h2>
        <span className="label">Up to 20 points a game</span>
      </div>
      <GameDoors />

      <section className="tray">
        <div className="tray-head">
          <h3>On the counter</h3>
        </div>
        <Dishes dishes={service.menu} />
      </section>
    </div>
  );
}
