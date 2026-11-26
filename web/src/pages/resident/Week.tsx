// The food chart for the week ahead, with "I am going home" in one step.

import { useState } from "react";

import { MealCard, type RsvpResult } from "../../components/MealCard";
import { Loading, Problem, useToast } from "../../components/ui";
import { api, type MealsResponse } from "../../lib/api";
import { addDays, dayLabel } from "../../lib/format";
import { useApi, useNow, useSession } from "../../lib/session";

export function Week() {
  const { patch } = useSession();
  const toast = useToast();
  const meals = useApi<MealsResponse>("/api/meals?days=8");
  const now = useNow();
  const [range, setRange] = useState<{ start: string; end: string } | null>(null);
  const [saving, setSaving] = useState(false);

  if (meals.error && !meals.data) return <Problem message={meals.error} retry={meals.reload} />;
  if (!meals.data) return <Loading lines={3} />;

  const today = meals.data.today;
  const start = range?.start ?? addDays(today, 1);
  const end = range?.end ?? addDays(today, 2);
  const changed = (result: RsvpResult) => {
    patch({ points: result.points, streak: result.streak });
    meals.reload();
  };
  const markAway = async () => {
    setSaving(true);
    try {
      const result = await api<{ marked: number; gained: number; points: number }>("/api/meals/away", { method: "POST", body: { start, end } });
      patch({ points: result.points });
      meals.reload();
      toast(`${result.marked} meals marked. The kitchen will not cook for you.${result.gained ? ` +${result.gained} points` : ""}`);
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={meals.stale ? "stack stale" : "stack"}>
      <section className="tray">
        <div className="tray-head">
          <h2>Going home?</h2>
          <span className="label">Skips every meal</span>
        </div>
        <div className="tray-body stack" style={{ gap: 10 }}>
          <div className="grid two" style={{ gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <label className="field">
              <span className="label">From</span>
              <input className="input" type="date" value={start} min={today} max={addDays(today, 60)} onChange={(event) => setRange({ start: event.target.value, end: event.target.value > end ? event.target.value : end })} />
            </label>
            <label className="field">
              <span className="label">To</span>
              <input className="input" type="date" value={end} min={start} max={addDays(start, 20)} onChange={(event) => setRange({ start, end: event.target.value })} />
            </label>
          </div>
          <button className="btn block" onClick={markAway} disabled={saving || !start || !end}>
            Mark me away
          </button>
        </div>
      </section>

      {meals.data.days.map((day, index) => (
        <section className="stack" key={day.day} style={{ gap: 10 }}>
          <div className="day-head">
            <h2>{index === 0 ? "Today" : day.weekday}</h2>
            <span className="label">{dayLabel(day.day)}</span>
          </div>
          {day.calendar && <span className="tag warn" style={{ justifySelf: "start" }}>{day.calendar.label}</span>}
          {day.meals.map((meal) => (
            <MealCard key={meal.meal} meal={meal} now={now} onChanged={changed} />
          ))}
        </section>
      ))}
    </div>
  );
}
