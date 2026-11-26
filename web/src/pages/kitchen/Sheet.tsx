// The cook sheet: how many to expect and how much of each dish to put on the fire.

import { useState } from "react";

import { Loading, PageHead, Problem, Readout, VegMark } from "../../components/ui";
import type { CookSheet } from "../../lib/api";
import { clock, dayLabel, kg, MEAL_LABEL, num, rupees } from "../../lib/format";
import { useApi } from "../../lib/session";

export function Sheet() {
  const [pick, setPick] = useState<string>("");
  const [day, meal] = pick ? pick.split("|") : ["", ""];
  const sheet = useApi<CookSheet>(pick ? `/api/kitchen/sheet?day=${day}&meal=${meal}` : "/api/kitchen/sheet", 60000);

  if (sheet.error && !sheet.data) return <Problem message={sheet.error} retry={sheet.reload} />;
  if (!sheet.data) return <Loading lines={3} />;
  const data = sheet.data;
  const head = data.headcount;
  const risk = Math.round((1 - data.service_level) * 100);

  return (
    <>
      <PageHead
        eyebrow="Cook sheet"
        title={`${MEAL_LABEL[data.meal]}, ${dayLabel(data.day, "long")}`}
        sub={
          data.final
            ? `Final. Skip notices closed at ${clock(data.cutoff_at)}; service starts at ${clock(data.starts_at)}.`
            : `Preliminary. Skip notices close at ${clock(data.cutoff_at)} and the sheet becomes final then.`
        }
      >
        <select className="input" style={{ width: "auto" }} value={`${data.day}|${data.meal}`} onChange={(event) => setPick(event.target.value)} aria-label="Sitting">
          {data.sittings.map((sitting) => (
            <option key={`${sitting.day}|${sitting.meal}`} value={`${sitting.day}|${sitting.meal}`}>
              {dayLabel(sitting.day)} · {MEAL_LABEL[sitting.meal]}
            </option>
          ))}
        </select>
        <button className="btn ghost" onClick={() => window.print()}>
          Print
        </button>
      </PageHead>

      <div className={sheet.stale ? "stack stale" : "stack"}>
        <div className="row">
          <span className={data.final ? "tag solid" : "tag warn"}>{data.final ? "Final" : "Preliminary"}</span>
          {data.calendar && <span className="tag warn">{data.calendar.label}</span>}
          {head.model && <span className="tag">Forecast: {head.model}</span>}
        </div>

        <section className="tray readouts">
          <Readout label="Expect" value={num(head.expected)} unit="residents">
            {head.low !== null && (
              <span>
                likely {num(head.low)} to {num(head.high)} of {num(head.roll)}
              </span>
            )}
          </Readout>
          <Readout label="Skip notices" value={num(head.notices)}>
            <span>{data.final ? "counted in the forecast" : "still coming in"}</span>
          </Readout>
          <Readout label="Same meal last week" value={num(head.last_week)} unit="served" />
          <Readout label="Cook in total" value={kg(data.totals.advised_kg)} unit="kg">
            {data.totals.saving_kg > 0 ? (
              <span>
                <span className="good">{kg(data.totals.saving_kg)} kg less</span> than the old fixed rule ({rupees(data.totals.saving_cost)})
              </span>
            ) : (
              <span>{kg(-data.totals.saving_kg)} kg more than the old fixed rule</span>
            )}
          </Readout>
        </section>

        <section className="tray">
          <div className="tray-head">
            <h2>Quantities</h2>
            <span className="label">Cooked weight</span>
          </div>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Dish</th>
                  <th className="num">Cook</th>
                  <th className="num">About</th>
                  <th className="num">Per head</th>
                  <th className="num">Old rule</th>
                  <th>Raw material</th>
                </tr>
              </thead>
              <tbody>
                {data.dishes.map((dish) => (
                  <tr key={dish.dish_id}>
                    <td>
                      <span className="dish-name">
                        <VegMark veg={dish.veg} />
                        {dish.name}
                      </span>
                    </td>
                    <td className="num" style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>
                      {dish.advised_kg === null ? "–" : `${dish.advised_kg.toFixed(1)} kg`}
                    </td>
                    <td className="num">{dish.pieces ? `${num(dish.pieces)} pcs` : ""}</td>
                    <td className="num">{dish.per_head_g ? `${dish.per_head_g} g` : "–"}</td>
                    <td className="num muted">{dish.rule_kg === null ? "–" : `${dish.rule_kg.toFixed(1)} kg`}</td>
                    <td className="muted" style={{ fontSize: 13 }}>
                      {dish.ingredients.map((item) => `${item.name} ${item.kg} kg`).join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tray-note">
            Each quantity is the expected demand plus a margin sized so a pot runs dry at most about {risk} time{risk === 1 ? "" : "s"} in 100. The mess manager sets that level.
          </p>
        </section>
      </div>
    </>
  );
}
