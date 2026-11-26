// The manager's first screen: how much is wasted, what it costs, and what changed since the cook sheet.

import { useState } from "react";

import { Bowl, ChartSwitch, Legend, StackedColumns, type Column } from "../../components/charts";
import { Change, Loading, PageHead, Problem, Readout } from "../../components/ui";
import type { Overview as OverviewData } from "../../lib/api";
import { dayLabel, kg, num, pct, rupees } from "../../lib/format";
import { useApi } from "../../lib/session";

const SERIES = [
  { name: "Left in the pots", color: "var(--s1)" },
  { name: "Left on plates", color: "var(--s2)" },
  { name: "Peels and trimmings", color: "var(--s3)" },
];
const RANGES: [number, string][] = [
  [28, "4 weeks"],
  [56, "8 weeks"],
  [126, "18 weeks"],
];

export function Overview() {
  const [days, setDays] = useState(28);
  const view = useApi<OverviewData>(`/api/manager/overview?days=${days}`);

  if (view.error && !view.data) return <Problem message={view.error} retry={view.reload} />;
  if (!view.data) return <Loading lines={3} />;
  const data = view.data;
  if (data.empty) {
    return (
      <>
        <PageHead eyebrow="Overview" title={data.tenant.name} />
        <p className="empty tray">Nothing has been weighed yet. Once the kitchen logs its first sittings, waste and forecasts appear here.</p>
      </>
    );
  }

  const { current, previous, adoption } = data;
  const compare = `vs the ${days / 7} weeks before`;
  const columns: Column[] = data.trend.map((week) => ({
    key: week.week,
    label: `Week of ${dayLabel(week.week, "tiny")}`,
    tick: dayLabel(week.week, "tiny"),
    values: [week.leftover_kg, week.plate_kg, week.prep_kg],
    notes: [...week.labels, `${pct(week.leftover_pct)} of cooked food never served`],
    flag: week.labels.length > 0,
  }));
  const firstSheetWeek = data.trend.findIndex((week) => week.phase === "sheet");

  return (
    <>
      <PageHead eyebrow="Overview" title={`${data.tenant.name} mess`} sub={`${dayLabel(data.range.from)} to ${dayLabel(data.range.to)} · ${num(current.sittings)} sittings · ${num(current.served)} plates served`}>
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
          <Readout label="Waste per plate served" value={num(current.waste_per_head_g)} unit="g">
            <Change now={current.waste_per_head_g} before={previous.waste_per_head_g} suffix={compare} />
          </Readout>
          <Readout label="Cooked, never served" value={pct(current.leftover_pct)}>
            <Change now={current.leftover_pct} before={previous.leftover_pct} suffix={compare} />
          </Readout>
          <Readout label="Head-count forecast error" value={pct(current.forecast_mape)}>
            <span>off by {num(current.forecast_mae)} residents per sitting on average</span>
          </Readout>
          <Readout label="Cost of what was wasted" value={rupees(current.cost)}>
            <span>
              {num(current.meals_equivalent)} full meals · {num(current.co2_kg)} kg CO2e
            </span>
          </Readout>
        </section>

        {adoption && (
          <section className="tray">
            <div className="tray-head">
              <h2>Since the kitchen started cooking from the sheet</h2>
              <span className="label">From {dayLabel(adoption.since)}</span>
            </div>
            <div className="tray-body grid wide-left" style={{ alignItems: "center" }}>
              <div className="row" style={{ justifyContent: "space-around", gap: 20 }}>
                <Bowl share={(adoption.before.leftover_pct ?? 0) / 25} value={pct(adoption.before.leftover_pct)} caption="Left in pots before" />
                <Bowl share={(adoption.after.leftover_pct ?? 0) / 25} value={pct(adoption.after.leftover_pct)} caption="Left in pots since" tone="good" />
                <div style={{ maxWidth: "30ch" }}>
                  <div className="figure" style={{ fontSize: 40 }}>
                    {num(adoption.saved_kg_per_week)}
                    <span className="unit">kg a week</span>
                  </div>
                  <p className="muted" style={{ marginTop: 6, fontSize: 13.5 }}>of food not cooked for nobody, against what the old fixed rule would have cooked on the same days for the same appetite.</p>
                </div>
              </div>
              <dl className="kv">
                <dt>Saved in ingredients</dt>
                <dd>{rupees(adoption.saved_cost_per_month)} a month</dd>
                <dt>Full meals not thrown away</dt>
                <dd>{num(adoption.saved_meals)}</dd>
                <dt>Emissions avoided</dt>
                <dd>{num(adoption.saved_co2_kg)} kg CO2e</dd>
                <dt>Pots that ran dry</dt>
                <dd>{pct(adoption.after.runout_pct)}</dd>
                <dt>Old rule, same days</dt>
                <dd>{pct(adoption.old_rule_runout_pct)}</dd>
              </dl>
            </div>
            <p className="tray-note">Cooking less only counts if nobody goes hungry: the last two lines compare how often a pot ran dry with the sheet and how often it would have with the old rule.</p>
          </section>
        )}

        <section className="tray">
          <div className="tray-head">
            <h2>Waste by week</h2>
            <Legend items={SERIES} />
          </div>
          <div className="tray-body">
            <ChartSwitch
              chart={<StackedColumns columns={columns} series={SERIES} unit="kg" divider={firstSheetWeek > 0 ? { index: firstSheetWeek, label: "Cook sheet in use" } : undefined} />}
              table={
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Week of</th>
                        <th className="num">In pots</th>
                        <th className="num">On plates</th>
                        <th className="num">Trimmings</th>
                        <th className="num">Never served</th>
                        <th className="num">Ran dry</th>
                        <th>Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.trend.map((week) => (
                        <tr key={week.week}>
                          <td>{dayLabel(week.week)}</td>
                          <td className="num">{kg(week.leftover_kg)} kg</td>
                          <td className="num">{kg(week.plate_kg)} kg</td>
                          <td className="num">{kg(week.prep_kg)} kg</td>
                          <td className="num">{pct(week.leftover_pct)}</td>
                          <td className="num">{pct(week.runout_pct)}</td>
                          <td className="muted" style={{ fontSize: 13 }}>{[week.phase === "sheet" ? "Sheet" : "Old rule", ...week.labels].join(" · ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              }
            />
          </div>
          <p className="tray-note">A dot under a week marks a holiday, break, exam or fest. Hover a column for the detail.</p>
        </section>

        <section className="tray">
          <div className="tray-head">
            <h2>Worth a look</h2>
            <span className="label">Last 4 weeks</span>
          </div>
          <div style={{ marginTop: 8 }}>
            {data.insights.map((insight) => (
              <div className={`insight ${insight.tone}`} key={insight.title}>
                <span className="metric">{insight.metric}</span>
                <div>
                  <h3>{insight.title}</h3>
                  <p>{insight.body}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
