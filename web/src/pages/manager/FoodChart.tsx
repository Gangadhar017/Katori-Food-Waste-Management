// The weekly food chart: what is planned for each sitting, how each dish is doing, and swaps worth making.

import { Fragment, useState } from "react";

import { Loading, Modal, PageHead, Problem, VegMark, useToast } from "../../components/ui";
import { api, type MealName, type MenuDish, type MenuView } from "../../lib/api";
import { MEAL_LABEL, MEALS, num, pct, parseDay, WEEKDAYS } from "../../lib/format";
import { useApi, useSession } from "../../lib/session";

const ALLOWED: Record<MealName, string[]> = {
  breakfast: ["breakfast", "side", "beverage"],
  lunch: ["staple", "dal", "sabzi", "special", "side", "dessert"],
  snacks: ["snack", "beverage"],
  dinner: ["staple", "dal", "sabzi", "special", "side", "dessert"],
};

function DishStats({ dish }: { dish: MenuDish }) {
  if (!dish.times) return <small>not served yet</small>;
  return (
    <small>
      {dish.rating === null ? "" : `${dish.rating.toFixed(1)}★ · `}
      {pct(dish.leftover_pct, 0)} left · {dish.times}×
    </small>
  );
}

function SlotEditor({ weekday, meal, ids, dishes, onClose, onSave }: { weekday: number; meal: MealName; ids: number[]; dishes: Map<number, MenuDish>; onClose: () => void; onSave: (ids: number[]) => Promise<void> }) {
  const [chosen, setChosen] = useState(ids);
  const [saving, setSaving] = useState(false);
  const [kind, setKind] = useState(ALLOWED[meal][0]);
  const options = [...dishes.values()].filter((dish) => dish.category === kind && !chosen.includes(dish.id)).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
  const changed = chosen.join() !== ids.join();
  return (
    <Modal title={`${WEEKDAYS[weekday]} ${MEAL_LABEL[meal].toLowerCase()}`} onClose={onClose}>
      <div className="stack" style={{ gap: 6 }}>
        <span className="label">On the chart</span>
        {chosen.map((id) => {
          const dish = dishes.get(id)!;
          return (
            <div className="pick" key={id} style={{ gridTemplateColumns: "auto 1fr auto auto" }}>
              <VegMark veg={dish.veg} />
              <span>
                <b style={{ fontWeight: 600 }}>{dish.name}</b>
              </span>
              <DishStats dish={dish} />
              <button className="btn ghost small" disabled={chosen.length <= 1} onClick={() => setChosen(chosen.filter((x) => x !== id))} aria-label={`Remove ${dish.name}`}>
                Remove
              </button>
            </div>
          );
        })}
      </div>
      <div className="stack" style={{ gap: 8 }}>
        <span className="label">Add a dish</span>
        <div className="seg" style={{ flexWrap: "wrap" }}>
          {ALLOWED[meal].map((category) => (
            <button key={category} aria-pressed={kind === category} onClick={() => setKind(category)} style={{ textTransform: "capitalize" }}>
              {category}
            </button>
          ))}
        </div>
        <div className="pick-list">
          {options.map((dish) => (
            <button className="pick" key={dish.id} disabled={chosen.length >= 8} onClick={() => setChosen([...chosen, dish.id])}>
              <VegMark veg={dish.veg} />
              <span>{dish.name}</span>
              <DishStats dish={dish} />
            </button>
          ))}
          {options.length === 0 && <span className="muted">Every {kind} dish is already on this meal.</span>}
        </div>
      </div>
      <button
        className="btn copper block"
        disabled={!changed || saving}
        onClick={async () => {
          setSaving(true);
          await onSave(chosen);
          setSaving(false);
        }}
      >
        {changed ? "Save and re-forecast the coming days" : "No changes"}
      </button>
    </Modal>
  );
}

export function FoodChart() {
  const { user } = useSession();
  const toast = useToast();
  const view = useApi<MenuView>("/api/manager/menu");
  const [editing, setEditing] = useState<{ weekday: number; meal: MealName } | null>(null);
  const [applying, setApplying] = useState(false);

  if (view.error && !view.data) return <Problem message={view.error} retry={view.reload} />;
  if (!view.data || !user) return <Loading lines={3} />;
  const data = view.data;
  const dishes = new Map(data.dishes.map((dish) => [dish.id, dish]));
  const today = parseDay(user.tenant.today).weekday;

  const save = async (weekday: number, meal: MealName, ids: number[], message: string) => {
    try {
      view.set(await api<MenuView>("/api/manager/menu", { method: "PUT", body: { weekday, meal, dish_ids: ids } }));
      setEditing(null);
      toast(message);
    } catch (error) {
      toast((error as Error).message);
    }
  };

  return (
    <>
      <PageHead eyebrow="Food chart" title="The week on the counter" sub="This is the chart residents see. Change a sitting and the coming days pick it up at once, with new forecasts and cook sheets." />
      <div className="stack">
        {data.suggestions.length > 0 && (
          <section className="tray">
            <div className="tray-head">
              <h2>Swaps worth making</h2>
              <span className="label">From ratings, leftovers and turnout</span>
            </div>
            <div style={{ marginTop: 8 }}>
              {data.suggestions.map((swap) => (
                <div className="insight" key={`${swap.weekday}-${swap.meal}-${swap.remove.id}`} style={{ gridTemplateColumns: "1fr auto", alignItems: "center" }}>
                  <div>
                    <h3>
                      {WEEKDAYS[swap.weekday]} {MEAL_LABEL[swap.meal].toLowerCase()}: {swap.remove.name} → {swap.add.name}
                    </h3>
                    <p>
                      {swap.remove.name} is {swap.reasons.join(", ")}. {swap.add.name} is rated {swap.add.rating?.toFixed(1)}
                      {swap.turnout_gain && swap.turnout_gain > 1 ? ` and should bring about ${num(swap.turnout_gain)} more residents` : ""}.{" "}
                      {swap.cost_per_plate > 0 ? `Costs ₹${swap.cost_per_plate.toFixed(1)} more a plate.` : swap.cost_per_plate < 0 ? `Saves ₹${(-swap.cost_per_plate).toFixed(1)} a plate.` : ""}
                    </p>
                  </div>
                  <button
                    className="btn ghost small"
                    disabled={applying}
                    onClick={async () => {
                      setApplying(true);
                      const ids = data.chart[swap.weekday].meals[swap.meal].map((id) => (id === swap.remove.id ? swap.add.id : id));
                      await save(swap.weekday, swap.meal, ids, `${swap.add.name} is on the chart for ${WEEKDAYS[swap.weekday]}.`);
                      setApplying(false);
                    }}
                  >
                    Make the swap
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="scroll-x">
          <div className="chart-grid">
            <div className="head" />
            {MEALS.map((meal) => (
              <div className="head" key={meal}>{MEAL_LABEL[meal]}</div>
            ))}
            {data.chart.map((day) => (
              <Fragment key={day.weekday}>
                <div className={day.weekday === today ? "today" : ""}>
                  <span className="dayname">{WEEKDAYS[day.weekday]}</span>
                  {day.weekday === today && <span className="label" style={{ display: "block", marginTop: 3 }}>Today</span>}
                </div>
                {MEALS.map((meal) => (
                  <div className="chart-cell" key={meal}>
                    <button className="cell-edit" onClick={() => setEditing({ weekday: day.weekday, meal })} aria-label={`Edit ${WEEKDAYS[day.weekday]} ${meal}`}>
                      {day.meals[meal].map((id) => {
                        const dish = dishes.get(id);
                        if (!dish) return null;
                        const weak = dish.rating !== null && dish.rating < 3;
                        return (
                          <span className="chart-dish" key={id}>
                            <VegMark veg={dish.veg} />
                            {dish.name}
                            {weak && <span className="flag" title="Rated under 3 stars">{dish.rating!.toFixed(1)}★</span>}
                          </span>
                        );
                      })}
                    </button>
                  </div>
                ))}
              </Fragment>
            ))}
          </div>
        </div>
        <p className="muted" style={{ fontSize: 13 }}>Click a sitting to change it. A red figure is a dish rated under three stars.</p>
      </div>
      {editing && (
        <SlotEditor
          weekday={editing.weekday}
          meal={editing.meal}
          ids={data.chart[editing.weekday].meals[editing.meal]}
          dishes={dishes}
          onClose={() => setEditing(null)}
          onSave={(ids) => save(editing.weekday, editing.meal, ids, "Chart saved. The coming days have new forecasts.")}
        />
      )}
    </>
  );
}
