// Forecast against what happened, the week ahead, and the dial that trades waste against empty pots.

import { useState } from "react";

import { BarList, ChartSwitch, ForecastChart, Legend, type ForecastDot } from "../../components/charts";
import { Loading, PageHead, Problem, Readout, useToast } from "../../components/ui";
import { api, type ForecastPoint, type ForecastView, type MealName, type TenantInfo } from "../../lib/api";
import { dayLabel, MEAL_LABEL, MEALS, num, pct } from "../../lib/format";
import { useApi, useSession } from "../../lib/session";

const LEVELS: [number, string, string][] = [
  [0.9, "Lean", "a pot may run dry about 1 time in 10"],
  [0.95, "Balanced", "about 1 time in 20"],
  [0.98, "Safe", "about 1 time in 50"],
];

export function Forecast() {
  const { user, refresh } = useSession();
  const toast = useToast();
  const view = useApi<ForecastView>("/api/manager/forecast", 120000);
  const [saving, setSaving] = useState(false);
  const [meal, setMeal] = useState<MealName | "all">("dinner");

  if (view.error && !view.data) return <Problem message={view.error} retry={view.reload} />;
  if (!view.data || !user) return <Loading lines={3} />;
  const data = view.data;
  const level = user.tenant.service_level;

  const dot = (point: ForecastPoint, future: boolean): ForecastDot => ({
    key: `${point.day}-${point.meal}`,
    label: `${dayLabel(point.day)} · ${MEAL_LABEL[point.meal]}`,
    dayTick: meal !== "all" || point.meal === "breakfast" ? dayLabel(point.day, "tiny") : null,
    forecast: (future ? point.expected : point.forecast) ?? null,
    low: point.low,
    high: point.high,
    actual: future ? null : (point.actual ?? null),
    note: point.label || (point.kind ? point.kind : undefined),
  });
  const wanted = (point: ForecastPoint) => meal === "all" || point.meal === meal;
  const past = data.recent.filter(wanted);
  const points = [...past.map((p) => dot(p, false)), ...data.upcoming.filter(wanted).map((p) => dot(p, true))];

  const byDay = new Map<string, Partial<Record<MealName, ForecastPoint>>>();
  for (const point of data.upcoming) byDay.set(point.day, { ...(byDay.get(point.day) ?? {}), [point.meal]: point });

  const setLevel = async (value: number) => {
    setSaving(true);
    try {
      await api<TenantInfo>("/api/manager/settings", { method: "PUT", body: { service_level: value } });
      await refresh();
      view.reload();
      toast("Saved. Every sheet that is not final yet has been recalculated.");
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHead eyebrow="Forecast" title="Head count, sitting by sitting" sub="Every forecast is written down before the meal and never changed afterwards, so this page scores the model on days it had not seen." />
      <div className={view.stale ? "stack stale" : "stack"}>
        <section className="tray readouts">
          <Readout label="Typical miss, last 4 weeks" value={num(data.live.mae, 1)} unit="residents">
            <span>out of {num(data.strength)} on the roll</span>
          </Readout>
          <Readout label="As a share of turnout" value={pct(data.live.mape)}>
            <span>mean absolute error, breaks included</span>
          </Readout>
          <Readout label="Inside the stated range" value={pct(data.live.in_band_pct, 0)}>
            <span>the range is built to hold 80% of the time</span>
          </Readout>
          <Readout label="Sittings scored" value={num(data.live.sittings)} />
        </section>

        <section className="tray">
          <div className="tray-head">
            <h2>Forecast and what happened</h2>
            <Legend
              items={[
                { name: "Forecast", color: "var(--s1)", shape: "line" },
                { name: "Likely range", color: "var(--s1)", shape: "band" },
                { name: "Residents served", color: "var(--s2)", shape: "line" },
              ]}
            />
          </div>
          <div className="tray-body">
            <ChartSwitch
              filters={
                <div className="seg" role="group" aria-label="Meal">
                  {MEALS.map((name) => (
                    <button key={name} aria-pressed={meal === name} onClick={() => setMeal(name)}>
                      {MEAL_LABEL[name]}
                    </button>
                  ))}
                  <button aria-pressed={meal === "all"} onClick={() => setMeal("all")}>
                    All
                  </button>
                </div>
              }
              chart={<ForecastChart points={points} ceiling={data.strength} splitAt={past.length} />}
              table={
                <div className="table-wrap" style={{ maxHeight: 360, overflowY: "auto" }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Sitting</th>
                        <th className="num">Forecast</th>
                        <th className="num">Range</th>
                        <th className="num">Served</th>
                        <th className="num">Off by</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...points].reverse().map((point) => (
                        <tr key={point.key}>
                          <td>{point.label}</td>
                          <td className="num">{num(point.forecast)}</td>
                          <td className="num">{point.low === null ? "–" : `${num(point.low)}–${num(point.high)}`}</td>
                          <td className="num">{point.actual === null ? "to come" : num(point.actual)}</td>
                          <td className="num">{point.actual === null || point.forecast === null ? "" : num(Math.abs(point.actual - point.forecast))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              }
            />
          </div>
        </section>

        <div className="grid wide-left">
          <section className="tray">
            <div className="tray-head">
              <h2>The week ahead</h2>
              <span className="label">Expected residents, with the likely range</span>
            </div>
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Day</th>
                    {MEALS.map((meal) => (
                      <th className="num" key={meal}>{MEAL_LABEL[meal]}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...byDay.entries()].map(([day, meals]) => {
                    const label = Object.values(meals).find((m) => m?.label)?.label;
                    return (
                      <tr key={day}>
                        <td>
                          {dayLabel(day)}
                          {label && <span className="tag warn" style={{ marginLeft: 8 }}>{label}</span>}
                        </td>
                        {MEALS.map((meal) => {
                          const point = meals[meal];
                          return (
                            <td className="num" key={meal}>
                              {point ? (
                                <>
                                  <span style={{ color: "var(--ink)", fontWeight: 600, fontSize: 13.5 }}>
                                    {num(point.expected)}
                                    {point.final && <span title="Final: skip notices have closed"> ●</span>}
                                  </span>
                                  <span className="cell-range">{point.low === null ? "" : `${num(point.low)}–${num(point.high)}`}</span>
                                </>
                              ) : (
                                ""
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="tray-note">● marks a final cook-sheet forecast. The rest are the week-ahead outlook, which does not know the skip notices yet and is weaker around holidays.</p>
          </section>

          <div className="stack">
            <section className="tray">
              <div className="tray-head">
                <h2>How careful should the kitchen be?</h2>
              </div>
              <div className="tray-body stack" style={{ gap: 10 }}>
                <div className="seg" role="group" aria-label="Service level">
                  {LEVELS.map(([value, name]) => (
                    <button key={value} aria-pressed={Math.abs(level - value) < 0.005} disabled={saving} onClick={() => setLevel(value)}>
                      {name}
                    </button>
                  ))}
                </div>
                <p className="muted" style={{ fontSize: 13.5 }}>
                  The sheet adds a margin to every dish. {LEVELS.find(([value]) => Math.abs(level - value) < 0.005)?.[1] ?? "Custom"}: {LEVELS.find(([value]) => Math.abs(level - value) < 0.005)?.[2] ?? `${Math.round((1 - level) * 100)} in 100`}. A safer setting cooks more and wastes more; a leaner one does the opposite.
                </p>
              </div>
            </section>
            <section className="tray">
              <div className="tray-head">
                <h2>Miss by meal</h2>
                <span className="label">Residents</span>
              </div>
              <div className="tray-body">
                <BarList rows={data.live.by_meal.map((row) => ({ key: row.meal, label: MEAL_LABEL[row.meal], value: row.mae ?? 0, text: num(row.mae, 1) }))} />
              </div>
            </section>
          </div>
        </div>
      </div>
    </>
  );
}
