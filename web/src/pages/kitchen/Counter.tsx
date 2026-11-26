// The counter tablet: which token is at which counter, and a button to call the next one.

import { useState } from "react";
import { Link } from "react-router-dom";

import { Loading, PageHead, Readout, useToast } from "../../components/ui";
import { api, type LineSnapshot } from "../../lib/api";
import { clock, MEAL_LABEL, waitText } from "../../lib/format";
import { useLine, useSession } from "../../lib/session";

export function Counter() {
  const { user } = useSession();
  const { snapshot, live, push } = useLine({ kind: "member" });
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  if (!snapshot) return <Loading lines={2} />;
  const { service, line } = snapshot;

  const post = async (path: string, body: unknown) => {
    setBusy(true);
    try {
      push(await api<LineSnapshot>(path, { method: "POST", body }));
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const counters = Array.from({ length: line.counters }, (_, index) => index + 1);

  return (
    <>
      <PageHead
        eyebrow="Counter"
        title={`${MEAL_LABEL[service.meal]} line`}
        sub={
          service.preview
            ? `The counter opens at ${clock(service.opens_at)}. Until then the demo runs a simulated crowd so the line can be tried.`
            : `Serving until ${clock(service.closes_at)}. Residents see their token and place on their phones.`
        }
      >
        <span className="tag">{live ? "Live" : "Updating"}</span>
        {user && (
          <Link className="btn ghost" to={`/board/${user.tenant.slug}`} target="_blank">
            Open wall display
          </Link>
        )}
      </PageHead>

      <div className="stack">
        <section className="tray readouts">
          <Readout label="Waiting" value={line.waiting} unit="tokens" />
          <Readout label="Wait if joining now" value={<span style={{ fontSize: 22 }}>{waitText(line.join_wait_s)}</span>} />
          <Readout label="Counters open" value={line.counters}>
            <span className="row no-print" style={{ gap: 6 }}>
              <button className="btn ghost small" disabled={busy || line.counters <= 1} onClick={() => post("/api/line/counters", { open: line.counters - 1 })} aria-label="Close a counter">
                −
              </button>
              <button className="btn ghost small" disabled={busy || line.counters >= 4} onClick={() => post("/api/line/counters", { open: line.counters + 1 })} aria-label="Open another counter">
                +
              </button>
            </span>
          </Readout>
          <Readout label="Made to order" value={service.menu.filter((dish) => dish.slow).length} unit="dishes">
            <span>{service.menu.filter((dish) => dish.slow).map((dish) => dish.name).join(", ") || "nothing slows the line today"}</span>
          </Readout>
        </section>

        <div className="grid" style={{ gridTemplateColumns: `repeat(${Math.min(line.counters, 4)}, minmax(0, 1fr))` }}>
          {counters.map((counter) => {
            const serving = line.now_serving.find((s) => s.counter === counter);
            return (
              <section className="tray" key={counter}>
                <div className="tray-body stack" style={{ justifyItems: "center", gap: 12 }}>
                  <span className="label">Counter {counter}</span>
                  <span className="figure" style={{ fontSize: 64, color: serving ? "var(--copper-strong)" : "var(--ink-3)" }}>{serving ? serving.token : "–"}</span>
                  <button className="btn block" disabled={busy} onClick={() => post("/api/line/next", { counter })}>
                    Next token
                  </button>
                </div>
              </section>
            );
          })}
        </div>

        <section className="tray">
          <div className="tray-head">
            <h2>Next up</h2>
            <span className="label">{line.simulated ? "Simulated crowd moves on its own" : "Tap Next when a plate is served"}</span>
          </div>
          <div className="tray-body row" style={{ gap: 10 }}>
            {line.next_tokens.length === 0 && <span className="muted">Nobody is waiting.</span>}
            {line.next_tokens.map((token) => (
              <div className="token small" key={token}>
                <span className="token-num">{token}</span>
              </div>
            ))}
            {line.waiting > line.next_tokens.length && <span className="muted">and {line.waiting - line.next_tokens.length} more</span>}
          </div>
        </section>
      </div>
    </>
  );
}
