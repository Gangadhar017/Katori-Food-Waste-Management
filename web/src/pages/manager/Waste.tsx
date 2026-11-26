// Where the waste is: which dishes, which sittings, which kind.

import { useState } from "react";

import { BarList, ChartSwitch, Heatmap } from "../../components/charts";
import { Loading, PageHead, Problem, Readout, VegMark } from "../../components/ui";
import type { WasteView } from "../../lib/api";
import { dayLabel, kg, MEAL_LABEL, MEALS, num, pct, rupees, WEEKDAYS_SHORT } from "../../lib/format";
import { useApi } from "../../lib/session";

const RANGES: [number, string][] = [
  [28, "4 weeks"],
  [56, "8 weeks"],
  [126, "18 weeks"],
];

export function Waste() {
  const [days, setDays] = useState(28);
  const view = useApi<WasteView>(`/api/manager/waste?days=${days}`);

  if (view.error && !view.data) return <Problem message={view.error} retry={view.reload} />;
  if (!view.data) return <Loading lines={3} />;
  const data = view.data;
  if (data.empty) return <p className="empty tray">Nothing has been weighed yet.</p>;

  const totals = data.totals;
  const share = (part?: number) => (totals.waste_kg ? `${(((part ?? 0) / totals.waste_kg) * 100).toFixed(0)}% of all waste` : "");
  const worst = data.by_dish.filter((dish) => dish.leftover_kg > 0).slice(0, 12);
  const cell = new Map(data.heatmap.map((entry) => [`${entry.meal}-${entry.weekday}`, entry.waste_per_head_g]));

  return (
    <>
      <PageHead eyebrow="Waste" title="Where it goes" sub={`${dayLabel(data.range.from)} to ${dayLabel(data.range.to)} · ${kg(totals.waste_kg)} kg in all`}>
        <div className="seg" role="group" aria-label="Period">
          {RANGES.map(([value, text]) => (
            <button key={value} aria-pressed={days === value} onClick={() => setDays(value)}>
              {text}
            </button>
          ))}
        </div>
      </PageHead>

      <div className={view.stale ? "stack stale" : "stack"}>
        <section className="tray readouts">
          <Readout label="Left in the pots" value={kg(totals.leftover_kg)} unit="kg">
            <span>{share(totals.leftover_kg)} · cooked, never served</span>
          </Readout>
          <Readout label="Left on plates" value={kg(totals.plate_kg)} unit="kg">
            <span>{share(totals.plate_kg)} · served, not eaten</span>
          </Readout>
          <Readout label="Peels and trimmings" value={kg(totals.prep_kg)} unit="kg">
            <span>{share(totals.prep_kg)} · before cooking</span>
          </Readout>
          <Readout label="Pots that ran dry" value={pct(totals.runout_pct)}>
            <span>of all dishes served</span>
          </Readout>
        </section>

        <div className="grid wide-left">
          <section className="tray">
            <div className="tray-head">
              <h2>Dishes that come back</h2>
              <span className="label">Kilograms left in the pot</span>
            </div>
            <div className="tray-body">
              <ChartSwitch
                chart={
                  <BarList
                    rows={worst.map((dish) => ({
                      key: String(dish.dish_id),
                      label: (
                        <span className="dish-name" style={{ fontWeight: 520 }}>
                          <VegMark veg={dish.veg} />
                          {dish.name}
                        </span>
                      ),
                      value: dish.leftover_kg,
                      text: `${kg(dish.leftover_kg)} kg`,
                      title: `${dish.name}: ${pct(dish.leftover_pct)} of ${kg(dish.prepared_kg)} kg cooked over ${dish.times} sittings`,
                    }))}
                  />
                }
                table={
                  <div className="table-wrap" style={{ maxHeight: 420, overflowY: "auto" }}>
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Dish</th>
                          <th className="num">Served</th>
                          <th className="num">Cooked</th>
                          <th className="num">Left</th>
                          <th className="num">Share left</th>
                          <th className="num">Ran dry</th>
                          <th className="num">Rating</th>
                          <th className="num">Cost</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.by_dish.map((dish) => (
                          <tr key={dish.dish_id}>
                            <td>
                              <span className="dish-name">
                                <VegMark veg={dish.veg} />
                                {dish.name}
                              </span>
                            </td>
                            <td className="num">{dish.times}×</td>
                            <td className="num">{kg(dish.prepared_kg)} kg</td>
                            <td className="num">{kg(dish.leftover_kg)} kg</td>
                            <td className="num">{pct(dish.leftover_pct)}</td>
                            <td className="num">{dish.runouts || ""}</td>
                            <td className="num">{dish.rating === null ? "–" : `${dish.rating.toFixed(1)} ★`}</td>
                            <td className="num">{rupees(dish.cost)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                }
              />
            </div>
          </section>

          <section className="tray">
            <div className="tray-head">
              <h2>By meal</h2>
            </div>
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Meal</th>
                    <th className="num">Per plate</th>
                    <th className="num">Unserved</th>
                    <th className="num">Ran dry</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_meal.map((row) => (
                    <tr key={row.meal}>
                      <td>{MEAL_LABEL[row.meal]}</td>
                      <td className="num">{num(row.waste_per_head_g)} g</td>
                      <td className="num">{pct(row.leftover_pct)}</td>
                      <td className="num">{pct(row.runout_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="tray-head" style={{ borderTop: "1px solid var(--line)", paddingTop: 14, marginTop: 6 }}>
              <h2>By kind of dish</h2>
              <span className="label">Share left in pot</span>
            </div>
            <div className="tray-body">
              <BarList
                rows={data.by_category.map((row) => ({ key: row.category, label: <span style={{ textTransform: "capitalize" }}>{row.category}</span>, value: row.leftover_pct ?? 0, text: pct(row.leftover_pct), tone: "steel" as const, title: `${kg(row.leftover_kg)} kg left` }))}
              />
            </div>
          </section>
        </div>

        <section className="tray">
          <div className="tray-head">
            <h2>Waste per plate, by sitting</h2>
            <span className="label">Grams per resident served</span>
          </div>
          <div className="tray-body">
            <Heatmap rows={MEALS.map((meal) => ({ key: meal, label: MEAL_LABEL[meal] }))} columns={WEEKDAYS_SHORT} value={(meal, weekday) => cell.get(`${meal}-${weekday}`) ?? null} unit="g" />
          </div>
          <p className="tray-note">Darker means more thrown away for every person who ate. All three kinds of waste are counted.</p>
        </section>
      </div>
    </>
  );
}
