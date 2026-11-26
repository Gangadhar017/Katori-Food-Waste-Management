// The front door: what Katori does, proof from the demo hostel, and three ways in.

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Brand, Icon, useToast } from "../components/ui";
import { BinIt } from "../games/BinIt";
import { api, type PublicSummary, type Role } from "../lib/api";
import { num, pct } from "../lib/format";
import { HOME } from "../lib/routes";
import { useSession, useTheme } from "../lib/session";

const DOORS: { role: Role; title: string; text: string }[] = [
  { role: "student", title: "A resident", text: "See today's food chart, skip a meal in time, take a token, play while you wait." },
  { role: "kitchen", title: "The kitchen", text: "Read the cook sheet: how many to expect and how many kilos of each dish." },
  { role: "manager", title: "The mess manager", text: "Waste, cost, forecast accuracy, the weekly chart and the models behind it." },
];

const STEPS = [
  ["01", "Residents give notice", "One tap to skip a meal, or mark the days you are home. Every notice is a plate nobody has to guess about."],
  ["02", "The model forecasts", "Head count for every sitting from notices, the menu, the weekday, exams and holidays, retrained as the log grows."],
  ["03", "The kitchen cooks to the sheet", "Kilograms per dish with a safety margin sized from the model's own past errors, not a rule of thumb."],
  ["04", "Weigh what is left", "Pots and plate bins are weighed after service. That is what the model learns from, and what the manager sees."],
];

export function Landing() {
  const { user, enter, signIn } = useSession();
  const [theme, toggleTheme] = useTheme();
  const navigate = useNavigate();
  const toast = useToast();
  const [summary, setSummary] = useState<PublicSummary | null>(null);
  const [waking, setWaking] = useState(false);
  const [waited, setWaited] = useState(0);
  const [busy, setBusy] = useState<Role | "form" | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retry = 0;
    const started = Date.now();
    const slow = window.setTimeout(() => !cancelled && setWaking(true), 2500);
    const tick = window.setInterval(() => setWaited(Math.round((Date.now() - started) / 1000)), 1000);
    const attempt = async () => {
      try {
        const result = await api<PublicSummary>("/api/public/summary", { timeoutMs: 9000 });
        if (cancelled) return;
        setSummary(result);
        setWaking(false);
        window.clearTimeout(slow);
        window.clearInterval(tick);
      } catch {
        if (cancelled) return;
        setWaking(true);
        retry = window.setTimeout(attempt, 3000);
      }
    };
    attempt();
    return () => {
      cancelled = true;
      window.clearTimeout(slow);
      window.clearTimeout(retry);
      window.clearInterval(tick);
    };
  }, []);

  const go = async (role: Role) => {
    setBusy(role);
    try {
      await enter(role);
      navigate(HOME[role]);
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="landing">
      <header className="landing-top">
        <Brand sub="Mess waste, measured" />
        <div className="row" style={{ gap: 6 }}>
          {summary && (
            <Link className="btn ghost small" to={`/board/${summary.slug}`}>
              Wall display
            </Link>
          )}
          <button className="btn ghost small" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
            <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
          </button>
        </div>
      </header>

      <main>
        <section className="hero">
          <div>
            <p className="label">Food-waste forecasting for hostel messes</p>
            <h1 className="display" style={{ marginTop: 14 }}>
              Cook what will be <em>eaten.</em>
            </h1>
            <p className="hero-lede">
              Katori predicts how many residents will turn up for each meal, tells the kitchen how many kilograms of every dish to cook, and keeps the serving line moving with tokens instead of a queue.
            </p>
          </div>

          <div className="stack">
            {waking && !summary ? (
              <div className="wake tray" style={{ padding: 16 }}>
                <div>
                  <p className="label">Waking the kitchen · {waited}s</p>
                  <p style={{ marginTop: 6 }}>
                    The demo runs on free hosting that sleeps when nobody is around. It usually takes about forty seconds to start. Sort a few things while it does.
                  </p>
                </div>
                <BinIt seconds={30} />
              </div>
            ) : (
              <>
                <p className="label">Step into the demo hostel as</p>
                <div className="doors">
                  {user && (
                    <button className="door" onClick={() => navigate(HOME[user.role])}>
                      <span className="num">→</span>
                      <span>
                        <b>Carry on as {user.name}</b>
                        <small>You are already signed in.</small>
                      </span>
                      <span className="go">›</span>
                    </button>
                  )}
                  {DOORS.map((door, index) => (
                    <button className="door" key={door.role} onClick={() => go(door.role)} disabled={!summary || busy !== null} aria-busy={busy === door.role}>
                      <span className="num">0{index + 1}</span>
                      <span>
                        <b>{door.title}</b>
                        <small>{door.text}</small>
                      </span>
                      <span className="go">›</span>
                    </button>
                  ))}
                </div>
                <details>
                  <summary className="muted" style={{ cursor: "pointer", fontSize: 13.5 }}>
                    Your mess already uses Katori? Sign in
                  </summary>
                  <form
                    className="stack"
                    style={{ marginTop: 10, gap: 8 }}
                    onSubmit={async (event) => {
                      event.preventDefault();
                      const form = new FormData(event.currentTarget);
                      setBusy("form");
                      try {
                        const signedIn = await signIn(String(form.get("email")), String(form.get("password")));
                        navigate(HOME[signedIn.role]);
                      } catch (error) {
                        toast((error as Error).message);
                      } finally {
                        setBusy(null);
                      }
                    }}
                  >
                    <input className="input" name="email" type="email" placeholder="Email" autoComplete="username" required />
                    <input className="input" name="password" type="password" placeholder="Password" autoComplete="current-password" required />
                    <button className="btn" disabled={busy !== null}>
                      Sign in
                    </button>
                  </form>
                </details>
              </>
            )}
          </div>
        </section>

        {summary && (
          <section className="proof" aria-label="Results from the demo hostel">
            <div>
              <span className="label">Forecast error, last 4 weeks</span>
              <span className="figure">{pct(summary.forecast_mape)}</span>
              <span className="muted" style={{ fontSize: 13 }}>of head count, on ordinary days</span>
            </div>
            <div>
              <span className="label">Cooked but never served</span>
              <span className="figure">
                {pct(summary.leftover_before_pct, 0)} → {pct(summary.leftover_after_pct, 0)}
              </span>
              <span className="muted" style={{ fontSize: 13 }}>before and after the cook sheet</span>
            </div>
            <div>
              <span className="label">Food not cooked for nobody</span>
              <span className="figure">
                {num(summary.saved_kg_per_week)}
                <span className="unit">kg / week</span>
              </span>
              <span className="muted" style={{ fontSize: 13 }}>against the old fixed rule, same days</span>
            </div>
            <div>
              <span className="label">Sittings logged</span>
              <span className="figure">{num(summary.sittings_logged)}</span>
              <span className="muted" style={{ fontSize: 13 }}>
                {summary.weeks} weeks, {num(summary.residents)} residents
              </span>
            </div>
          </section>
        )}

        <section className="how" aria-label="How it works">
          {STEPS.map(([step, title, text]) => (
            <div key={step}>
              <span className="step">{step}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </section>
      </main>

      <footer className="landing-foot">
        <span>
          {summary?.simulated
            ? `${summary.hostel}, ${summary.city}, is a simulated hostel: its residents, menus and waste are generated, the models and their scores are real.`
            : "Katori"}
        </span>
        <span>Hostel mode. Restaurants next.</span>
      </footer>
    </div>
  );
}
