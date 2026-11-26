// A game screen that keeps an eye on the resident's token while they play.

import { useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { Icon, useToast } from "../../components/ui";
import { BinIt } from "../../games/BinIt";
import { JustEnough } from "../../games/JustEnough";
import { api } from "../../lib/api";
import { useLine, useSession } from "../../lib/session";
import { useTurnAlert } from "./Line";

interface ScoreResult {
  gained: number;
  points: number;
  best: number;
  scored_plays_left: number;
}

const TITLES: Record<string, string> = { "bin-it": "Bin It", "just-enough": "Just Enough" };

export function Play() {
  const { game = "" } = useParams();
  const { patch } = useSession();
  const toast = useToast();
  const { snapshot } = useLine({ kind: "member" });
  const [last, setLast] = useState<ScoreResult | null>(null);
  useTurnAlert(snapshot);

  if (!TITLES[game]) return <Navigate to="/line" replace />;
  const ticket = snapshot?.ticket;

  const finish = async (score: number) => {
    try {
      const result = await api<ScoreResult>("/api/games/score", { method: "POST", body: { game, score } });
      setLast(result);
      patch({ points: result.points });
      toast(result.gained ? `+${result.gained} points` : "No points this time: three scored games a day.");
    } catch (error) {
      toast((error as Error).message);
    }
  };

  return (
    <div className="stack">
      <div className="spread">
        <Link className="btn ghost small" to="/line">
          <Icon name="back" size={16} />
          Line
        </Link>
        {ticket && ticket.status !== "served" ? (
          <span className={ticket.status === "called" ? "tag copper" : "tag"} aria-live="polite">
            {ticket.status === "called" ? `Your turn · counter ${ticket.counter}` : `Token ${ticket.token} · ${ticket.ahead} ahead`}
          </span>
        ) : (
          <span className="label">{TITLES[game]}</span>
        )}
      </div>
      {game === "bin-it" ? <BinIt onFinish={finish} /> : <JustEnough onFinish={finish} />}
      {last && (
        <p className="muted" style={{ textAlign: "center", fontSize: 13.5 }}>
          Your best: {last.best}. {last.scored_plays_left ? `${last.scored_plays_left} more scored game${last.scored_plays_left > 1 ? "s" : ""} today.` : "Play on for fun; points come back tomorrow."}
        </p>
      )}
    </div>
  );
}
