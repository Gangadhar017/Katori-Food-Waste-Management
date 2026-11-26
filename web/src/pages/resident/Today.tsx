import { useState } from "react";

import { MealCard, RateModal, type RsvpResult } from "../../components/MealCard";
import { Loading, Problem } from "../../components/ui";
import type { Meal, MealsResponse } from "../../lib/api";
import { dayLabel } from "../../lib/format";
import { useApi, useNow, useSession } from "../../lib/session";

export function Today() {
  const { patch } = useSession();
  const meals = useApi<MealsResponse>("/api/meals?days=2", 60000);
  const now = useNow();
  const [rating, setRating] = useState<Meal | null>(null);

  if (meals.error && !meals.data) return <Problem message={meals.error} retry={meals.reload} />;
  if (!meals.data) return <Loading lines={3} />;

  const changed = (result: RsvpResult) => {
    patch({ points: result.points, streak: result.streak });
    meals.reload();
  };
  const [today, tomorrow] = meals.data.days;
  return (
    <div className={meals.stale ? "stack stale" : "stack"}>
      <div className="day-head">
        <h2>Today</h2>
        <span className="label">{dayLabel(today.day, "long")}</span>
      </div>
      {today.calendar && <span className="tag warn" style={{ justifySelf: "start" }}>{today.calendar.label}</span>}
      {today.meals.map((meal) => (
        <MealCard key={meal.meal} meal={meal} now={now} onChanged={changed} onRate={setRating} />
      ))}
      {tomorrow && (
        <>
          <div className="day-head" style={{ marginTop: 8 }}>
            <h2>Tomorrow</h2>
            <span className="label">{dayLabel(tomorrow.day, "long")}</span>
          </div>
          {tomorrow.calendar && <span className="tag warn" style={{ justifySelf: "start" }}>{tomorrow.calendar.label}</span>}
          {tomorrow.meals.map((meal) => (
            <MealCard key={meal.meal} meal={meal} now={now} onChanged={changed} />
          ))}
        </>
      )}
      {rating && (
        <RateModal
          meal={rating}
          onClose={() => setRating(null)}
          onSaved={(result) => {
            patch({ points: result.points, streak: result.streak });
            meals.reload();
          }}
        />
      )}
    </div>
  );
}
