// One sitting as a resident sees it: what is cooking, and the eat / skip switch.

import { useState } from "react";
import { Link } from "react-router-dom";

import { api, type Meal } from "../lib/api";
import { clock, countdown, MEAL_LABEL, num } from "../lib/format";
import { Dishes, Modal, StateTag, VegMark, useToast } from "./ui";

export interface RsvpResult {
  meal: Meal;
  points: number;
  gained: number;
  streak: number;
}

export function MealCard({ meal, now, onChanged, onRate }: { meal: Meal; now: number; onChanged: (result: RsvpResult) => void; onRate?: (meal: Meal) => void }) {
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const skipped = meal.rsvp === "skip";

  const set = async (status: "eat" | "skip") => {
    if (status === meal.rsvp || saving) return;
    setSaving(true);
    try {
      const result = await api<RsvpResult>(`/api/meals/${meal.day}/${meal.meal}/rsvp`, { method: "PUT", body: { status } });
      onChanged(result);
      toast(
        status === "skip"
          ? result.gained > 0
            ? `Noted. The kitchen will cook one plate less. +${result.gained} points`
            : "Noted. The kitchen will cook one plate less."
          : "You are back on the list for this meal.",
      );
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setSaving(false);
    }
  };

  let left: React.ReactNode;
  let right: React.ReactNode;
  if (meal.state === "open") {
    left = <span className="muted" style={{ fontSize: 13 }}>Notice closes in {countdown(meal.cutoff_at, now)}</span>;
    right = (
      <div className="switch" role="group" aria-label={`${MEAL_LABEL[meal.meal]}: eating or skipping`}>
        <button aria-pressed={!skipped} disabled={saving} onClick={() => set("eat")}>
          Eating
        </button>
        <button className="skip" aria-pressed={skipped} disabled={saving} onClick={() => set("skip")}>
          Skip
        </button>
      </div>
    );
  } else if (meal.state === "cooking") {
    left = <span className="muted" style={{ fontSize: 13 }}>The kitchen is cooking{meal.expected ? ` for about ${num(meal.expected)}` : ""}</span>;
    right = <span className={skipped ? "tag copper" : "tag"}>{skipped ? "You skipped" : "You are in"}</span>;
  } else if (meal.state === "serving") {
    left = <span className="muted" style={{ fontSize: 13 }}>Serving until {clock(meal.ends_at)}</span>;
    right = skipped ? (
      <span className="tag copper">You skipped</span>
    ) : (
      <Link className="btn copper small" to="/line">
        Take a token
      </Link>
    );
  } else {
    left = <span className="muted" style={{ fontSize: 13 }}>{skipped ? "You skipped this one" : "Served"}</span>;
    right = meal.rated ? (
      <span className="tag good">Rated</span>
    ) : meal.can_rate && onRate ? (
      <button className="btn ghost small" onClick={() => onRate(meal)}>
        Rate it
      </button>
    ) : null;
  }

  return (
    <article className={`tray meal ${skipped ? "skipped" : ""}`}>
      <div className="meal-top">
        <div>
          <div className="meal-name">{meal.meal}</div>
          <div className="meal-time">
            {clock(meal.starts_at)} – {clock(meal.ends_at)}
          </div>
        </div>
        <StateTag state={meal.state} />
      </div>
      <Dishes dishes={meal.dishes} />
      <div className="meal-foot">
        {left}
        {right}
      </div>
    </article>
  );
}

const PORTIONS: [string, string][] = [
  ["less", "Too little"],
  ["right", "Right"],
  ["more", "Too much"],
];

export function RateModal({ meal, onClose, onSaved }: { meal: Meal; onClose: () => void; onSaved: (result: { gained: number; points: number; streak: number }) => void }) {
  const toast = useToast();
  const dishes = meal.dishes.filter((dish) => dish.category !== "beverage");
  const [stars, setStars] = useState<Record<number, number>>({});
  const [portion, setPortion] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState(false);
  const rated = dishes.filter((dish) => stars[dish.id]);

  const save = async () => {
    setSaving(true);
    try {
      const result = await api<{ gained: number; points: number; streak: number }>(`/api/meals/${meal.day}/${meal.meal}/ratings`, {
        method: "POST",
        body: { ratings: rated.map((dish) => ({ dish_id: dish.id, stars: stars[dish.id], portion: portion[dish.id] ?? "right" })) },
      });
      onSaved(result);
      toast(result.gained ? `Thanks. The mess manager sees this. +${result.gained} points` : "Rating updated.");
      onClose();
    } catch (error) {
      toast((error as Error).message);
      setSaving(false);
    }
  };

  return (
    <Modal title={`How was ${meal.meal}?`} onClose={onClose}>
      <p className="muted" style={{ fontSize: 13.5 }}>Ratings decide what stays on the food chart. Rate as many dishes as you ate.</p>
      <div className="stack" style={{ gap: 12 }}>
        {dishes.map((dish) => (
          <div key={dish.id} className="stack" style={{ gap: 6, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <div className="spread">
              <span className="dish-name">
                <VegMark veg={dish.veg} />
                {dish.name}
              </span>
              <span className="stars" role="group" aria-label={`Stars for ${dish.name}`}>
                {[1, 2, 3, 4, 5].map((value) => (
                  <button key={value} className={value <= (stars[dish.id] ?? 0) ? "on" : ""} aria-label={`${value} star${value > 1 ? "s" : ""}`} aria-pressed={stars[dish.id] === value} onClick={() => setStars({ ...stars, [dish.id]: value })}>
                    ★
                  </button>
                ))}
              </span>
            </div>
            {stars[dish.id] ? (
              <div className="row" style={{ gap: 8 }}>
                <span className="label">Portion</span>
                <div className="seg">
                  {PORTIONS.map(([key, text]) => (
                    <button key={key} aria-pressed={(portion[dish.id] ?? "right") === key} onClick={() => setPortion({ ...portion, [dish.id]: key })}>
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <button className="btn copper block" disabled={!rated.length || saving} onClick={save}>
        {rated.length ? `Send ${rated.length} rating${rated.length > 1 ? "s" : ""}` : "Tap the stars to rate"}
      </button>
    </Modal>
  );
}
