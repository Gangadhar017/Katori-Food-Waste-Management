// The weigh-in: what was cooked, what stayed in the pots, what came back on plates.

import { useEffect, useState } from "react";

import { Loading, PageHead, Problem, VegMark, useToast } from "../../components/ui";
import { api, type SittingLog } from "../../lib/api";
import { clock, dayLabel, MEAL_LABEL, num } from "../../lib/format";
import { useApi } from "../../lib/session";

interface Row {
  prepared: string;
  leftover: string;
  ranOut: boolean;
  short: string;
}

const text = (value: number | null | undefined) => (value === null || value === undefined ? "" : String(value));
const parse = (value: string) => (value.trim() === "" ? NaN : Number(value));

export function Log() {
  const toast = useToast();
  const [pick, setPick] = useState("");
  const [day, meal] = pick ? pick.split("|") : ["", ""];
  const log = useApi<SittingLog>(pick ? `/api/kitchen/log?day=${day}&meal=${meal}` : "/api/kitchen/log");
  const [served, setServed] = useState("");
  const [prep, setPrep] = useState("");
  const [plate, setPlate] = useState("");
  const [rows, setRows] = useState<Record<number, Row>>({});
  const [saving, setSaving] = useState(false);

  const data = log.data;
  useEffect(() => {
    if (!data) return;
    setServed(text(data.served));
    setPrep(text(data.prep_waste_kg));
    setPlate(text(data.plate_waste_kg));
    setRows(
      Object.fromEntries(
        data.dishes.map((dish) => [dish.dish_id, { prepared: text(dish.prepared_kg ?? dish.advised_kg), leftover: text(dish.leftover_kg), ranOut: dish.ran_out, short: dish.short_heads ? String(dish.short_heads) : "" }]),
      ),
    );
  }, [data]);

  if (log.error && !data) return <Problem message={log.error} retry={log.reload} />;
  if (!data) return <Loading lines={3} />;

  const update = (id: number, change: Partial<Row>) => setRows((current) => ({ ...current, [id]: { ...current[id], ...change } }));
  const problems: string[] = [];
  if (!(parse(served) >= 0)) problems.push("Enter how many residents were served.");
  for (const dish of data.dishes) {
    const row = rows[dish.dish_id];
    if (!row) continue;
    if (!(parse(row.prepared) >= 0)) problems.push(`${dish.name}: enter the cooked weight.`);
    else if (!row.ranOut && !(parse(row.leftover) >= 0)) problems.push(`${dish.name}: enter what was left, or tick "ran out".`);
    else if (parse(row.leftover) > parse(row.prepared)) problems.push(`${dish.name}: more left over than was cooked.`);
  }
  const cooked = data.dishes.reduce((sum, dish) => sum + (parse(rows[dish.dish_id]?.prepared ?? "") || 0), 0);
  const left = data.dishes.reduce((sum, dish) => sum + (rows[dish.dish_id]?.ranOut ? 0 : parse(rows[dish.dish_id]?.leftover ?? "") || 0), 0);

  const save = async () => {
    setSaving(true);
    try {
      const saved = await api<SittingLog>(`/api/kitchen/log/${data.day}/${data.meal}`, {
        method: "PUT",
        body: {
          served: Math.round(parse(served)),
          prep_waste_kg: parse(prep) || 0,
          plate_waste_kg: parse(plate) || 0,
          dishes: data.dishes.map((dish) => {
            const row = rows[dish.dish_id];
            return { dish_id: dish.dish_id, prepared_kg: parse(row.prepared), leftover_kg: row.ranOut ? 0 : parse(row.leftover), ran_out: row.ranOut, short_heads: row.ranOut ? Math.round(parse(row.short) || 0) : 0 };
          }),
        },
      });
      log.set({ ...saved, sittings: data.sittings });
      toast("Weigh-in saved. The next retrain learns from it.");
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHead
        eyebrow="Weigh-in"
        title={`${MEAL_LABEL[data.meal]}, ${dayLabel(data.day, "long")}`}
        sub="Weigh each pot before it is washed and the plate bin before it is emptied. Two minutes here is what every forecast is built on."
      >
        <select className="input" style={{ width: "auto" }} value={`${data.day}|${data.meal}`} onChange={(event) => setPick(event.target.value)} aria-label="Sitting">
          {(data.sittings ?? []).map((sitting) => (
            <option key={`${sitting.day}|${sitting.meal}`} value={`${sitting.day}|${sitting.meal}`}>
              {dayLabel(sitting.day)} · {MEAL_LABEL[sitting.meal]}
            </option>
          ))}
        </select>
      </PageHead>

      <div className={log.stale ? "stack stale" : "stack"}>
        <div className="row">
          {data.logged ? (
            <span className="tag good">
              Logged {data.logged_by === "simulator" ? "by the simulator" : "by the kitchen"}
              {data.logged_at ? ` · ${clock(data.logged_at)}` : ""}
            </span>
          ) : (
            <span className="tag warn">Not logged yet</span>
          )}
          {data.logged_by === "simulator" && <span className="muted" style={{ fontSize: 13 }}>In the demo each sitting is logged automatically when it ends. You can correct it here.</span>}
        </div>

        <section className="tray">
          <div className="tray-body grid three">
            <label className="field">
              <span className="label">Residents served</span>
              <input className="input num" inputMode="numeric" value={served} onChange={(event) => setServed(event.target.value)} />
              {data.expected !== null && <span className="muted" style={{ fontSize: 12.5 }}>The sheet expected {num(data.expected)}</span>}
            </label>
            <label className="field">
              <span className="label">Plate bin (kg)</span>
              <input className="input num" inputMode="decimal" value={plate} onChange={(event) => setPlate(event.target.value)} />
              <span className="muted" style={{ fontSize: 12.5 }}>What residents left on their plates</span>
            </label>
            <label className="field">
              <span className="label">Peels and trimmings (kg)</span>
              <input className="input num" inputMode="decimal" value={prep} onChange={(event) => setPrep(event.target.value)} />
              <span className="muted" style={{ fontSize: 12.5 }}>Waste from preparation</span>
            </label>
          </div>
        </section>

        <section className="tray">
          <div className="tray-head">
            <h2>Pots</h2>
            <span className="label">
              {num(cooked, 1)} kg cooked · {num(left, 1)} kg left
            </span>
          </div>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Dish</th>
                  <th className="num">Sheet said</th>
                  <th className="num">Cooked (kg)</th>
                  <th className="num">Left in pot (kg)</th>
                  <th>Ran out</th>
                  <th className="num">Went without</th>
                </tr>
              </thead>
              <tbody>
                {data.dishes.map((dish) => {
                  const row = rows[dish.dish_id];
                  if (!row) return null;
                  return (
                    <tr key={dish.dish_id}>
                      <td>
                        <span className="dish-name">
                          <VegMark veg={dish.veg} />
                          {dish.name}
                        </span>
                      </td>
                      <td className="num muted">{dish.advised_kg === null ? "–" : `${dish.advised_kg.toFixed(1)} kg`}</td>
                      <td className="num">
                        <input className="input num" style={{ width: 96, minHeight: 34 }} inputMode="decimal" aria-label={`${dish.name}: cooked kg`} value={row.prepared} onChange={(event) => update(dish.dish_id, { prepared: event.target.value })} />
                      </td>
                      <td className="num">
                        <input className="input num" style={{ width: 96, minHeight: 34 }} inputMode="decimal" aria-label={`${dish.name}: left in pot kg`} disabled={row.ranOut} value={row.ranOut ? "0" : row.leftover} onChange={(event) => update(dish.dish_id, { leftover: event.target.value })} />
                      </td>
                      <td>
                        <label className="row" style={{ gap: 6, fontSize: 13 }}>
                          <input type="checkbox" checked={row.ranOut} onChange={(event) => update(dish.dish_id, { ranOut: event.target.checked })} />
                          Pot ran dry
                        </label>
                      </td>
                      <td className="num">
                        {row.ranOut && (
                          <input className="input num" style={{ width: 84, minHeight: 34 }} inputMode="numeric" placeholder="people" aria-label={`${dish.name}: residents who went without`} value={row.short} onChange={(event) => update(dish.dish_id, { short: event.target.value })} />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="tray-note">
            When a pot runs dry, note roughly how many people reached it empty. Without that the model only sees what was eaten, and would learn to cook too little.
          </p>
        </section>

        {problems.length > 0 && (
          <div className="notice">
            <div>{problems[0]}</div>
          </div>
        )}
        <div className="row no-print">
          <button className="btn copper" disabled={saving || problems.length > 0} onClick={save}>
            Save weigh-in
          </button>
          <button className="btn ghost" onClick={log.reload} disabled={saving}>
            Discard changes
          </button>
        </div>
      </div>
    </>
  );
}
