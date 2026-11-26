// The model report: what is serving, how it was chosen, what it leans on, and every training run.

import { useEffect } from "react";

import { BarList } from "../../components/charts";
import { Loading, PageHead, Problem, useToast } from "../../components/ui";
import { api, type ModelCard, type ModelsView } from "../../lib/api";
import { dayLabel, num, pct } from "../../lib/format";
import { useApi } from "../../lib/session";

function metric(card: ModelCard, key: string): number | null {
  const value = card.metrics?.[key];
  return typeof value === "number" ? value : null;
}

function Card({ card }: { card: ModelCard }) {
  if (!card.trained) {
    return (
      <section className="tray">
        <div className="tray-head">
          <h2>{card.title}</h2>
          <span className="tag warn">Not trained yet</span>
        </div>
        <p className="tray-body muted">{card.blurb} Needs four weeks of logged sittings.</p>
      </section>
    );
  }
  const chosen = card.candidates?.find((c) => c.key === card.algorithm);
  const baseline = card.candidates?.find((c) => c.key === card.metrics?.baseline);
  const skill = metric(card, "skill");
  const coverage = metric(card, "coverage_80");
  const digits = card.kind === "portion" ? 2 : 1;
  const policy = card.policy ?? {};
  return (
    <section className="tray">
      <div className="tray-head">
        <h2>{card.title}</h2>
        <span className="tag solid">{chosen?.label ?? card.algorithm}</span>
      </div>
      <div className="tray-body stack" style={{ gap: 14 }}>
        <p className="muted" style={{ fontSize: 13.5 }}>{card.blurb}</p>
        <div className="row" style={{ gap: 22, alignItems: "flex-end" }}>
          <div>
            <span className="label" style={{ display: "block", marginBottom: 6 }}>Typical miss in backtest</span>
            <span className="figure" style={{ fontSize: 30 }}>{metric(card, "mae")?.toFixed(digits)}</span>
            <span className="unit">{card.unit}</span>
          </div>
          {skill !== null && (
            <div>
              <span className="label" style={{ display: "block", marginBottom: 6 }}>Better than {baseline?.label.toLowerCase() ?? "the baseline"}</span>
              <span className="figure" style={{ fontSize: 30 }}>{(skill * 100).toFixed(0)}%</span>
            </div>
          )}
        </div>
        <div className="stack" style={{ gap: 8 }}>
          <span className="label">Candidates, scored on weeks they were not trained on</span>
          <BarList
            wide
            rows={(card.candidates ?? []).map((c) => ({
              key: c.key,
              label: (
                <span style={{ fontWeight: c.key === card.algorithm ? 680 : 480 }}>
                  {c.label}
                  {c.baseline ? " (naive)" : ""}
                </span>
              ),
              value: c.mae ?? 0,
              text: (c.mae ?? 0).toFixed(digits),
              tone: c.key === card.algorithm ? undefined : c.baseline ? "muted" : "steel",
            }))}
          />
        </div>
        {card.kind.startsWith("headcount") && (
          <dl className="kv">
            <dt>On ordinary days</dt>
            <dd>
              {metric(card, "ordinary_mae")?.toFixed(1)} residents ({pct(metric(card, "ordinary_mape"))})
            </dd>
            <dt>On holidays and breaks ({num(metric(card, "off_day_sittings"))} sittings)</dt>
            <dd>{metric(card, "off_day_mae")?.toFixed(1) ?? "–"} residents</dd>
            {coverage !== null && (
              <>
                <dt>80% range held, newest two weeks</dt>
                <dd>{pct(coverage * 100, 0)}</dd>
              </>
            )}
          </dl>
        )}
        {card.importance && card.importance.length > 0 && (
          <div className="stack" style={{ gap: 8 }}>
            <span className="label">What the forecast leans on</span>
            <BarList wide rows={card.importance.filter((item) => item.share > 0.005).map((item) => ({ key: item.group, label: item.group, value: item.share, text: pct(item.share * 100, 0), tone: "steel" as const, title: `Scrambling this input adds ${item.mae_rise} residents of error` }))} />
          </div>
        )}
        {policy.leftover_pct !== undefined && (
          <dl className="kv">
            <dt>Replay of the newest {policy.weeks} weeks: left in pots</dt>
            <dd>{pct(policy.leftover_pct)}</dd>
            <dt>Pots that would have run dry</dt>
            <dd>{pct(policy.runout_pct)}</dd>
            {policy.habit_leftover_pct !== undefined && (
              <>
                <dt>Old fixed rule, same days: left in pots</dt>
                <dd>{pct(policy.habit_leftover_pct)}</dd>
                <dt>Old fixed rule: ran dry</dt>
                <dd>{pct(policy.habit_runout_pct)}</dd>
              </>
            )}
            <dt>Safety margin on each dish</dt>
            <dd>{pct((policy.margin ?? 0) * 100)}</dd>
          </dl>
        )}
      </div>
      <p className="tray-note">
        Run #{card.run_id} · {num(card.rows)} rows · data through {card.train_through ? dayLabel(card.train_through) : "–"}
      </p>
    </section>
  );
}

export function Models() {
  const toast = useToast();
  const view = useApi<ModelsView>("/api/manager/models");
  const training = view.data?.training ?? false;
  const reload = view.reload;

  useEffect(() => {
    if (!training) return;
    const timer = window.setInterval(reload, 2500);
    return () => window.clearInterval(timer);
  }, [training, reload]);

  if (view.error && !view.data) return <Problem message={view.error} retry={view.reload} />;
  if (!view.data) return <Loading lines={3} />;
  const data = view.data;

  const retrain = async () => {
    try {
      await api("/api/manager/models/retrain", { method: "POST" });
      toast("Retraining all four models on the full log.");
      view.reload();
    } catch (error) {
      toast((error as Error).message);
    }
  };

  return (
    <>
      <PageHead
        eyebrow="Models"
        title="What is forecasting, and how well"
        sub="Each model is retrained as the log grows. A new run replaces the serving one only if it beats a naive baseline, and for head count only if it was not worse on the newest sittings."
      >
        {training ? <span className="tag warn">Training…</span> : data.last_result ? <span className="tag">{data.last_result}</span> : null}
        <button className="btn" onClick={retrain} disabled={training}>
          Retrain now
        </button>
      </PageHead>
      <div className="stack">
        <div className="grid two">
          {data.models.map((card) => (
            <Card card={card} key={card.kind} />
          ))}
        </div>
        <section className="tray">
          <div className="tray-head">
            <h2>Training runs</h2>
            <span className="label">Newest first</span>
          </div>
          <div className="table-wrap" style={{ marginTop: 8, maxHeight: 420, overflowY: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th className="num">Run</th>
                  <th>Trained</th>
                  <th>Model</th>
                  <th>Chosen</th>
                  <th className="num">Miss</th>
                  <th className="num">Naive</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((run) => (
                  <tr key={run.id}>
                    <td className="num">#{run.id}</td>
                    <td>{dayLabel(run.trained_at.slice(0, 10))}</td>
                    <td>{run.title}</td>
                    <td className="muted">{run.algorithm}</td>
                    <td className="num">{run.mae ?? "–"}</td>
                    <td className="num">{run.baseline_mae ?? "–"}</td>
                    <td>
                      <span className={run.status === "champion" ? "tag good" : run.status === "rejected" ? "tag bad" : "tag"}>{run.status === "champion" ? "Serving" : run.status === "rejected" ? "Rejected" : "Replaced"}</span>
                      <span className="muted" style={{ fontSize: 12.5, marginLeft: 8 }}>{run.note.split(":")[0]}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
}
