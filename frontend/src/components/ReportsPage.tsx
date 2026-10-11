import { useState } from "react";
import type { Decision } from "../api/schemas";
import type { Resource } from "../hooks/useCommandCenter";
import { summarizeDecisions } from "../lib/reports";
import { formatTime } from "../lib/utils";
import { DecisionHistory, DecisionInspection } from "./DecisionHistory";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";

export function ReportsPage({
  resource,
  refresh,
  onInspect,
  onEvaluate,
}: {
  resource: Resource<Decision[]>;
  refresh: () => void;
  onInspect: (id: string) => void;
  onEvaluate: () => void;
}) {
  const [chosenId, setChosenId] = useState("");
  const summary = resource.data ? summarizeDecisions(resource.data) : null;
  const selected =
    summary?.decisions.find((d) => d.decision_id === chosenId) ??
    summary?.decisions[0];
  const metrics = summary
    ? ([
        ["Loaded finalized decisions", summary.total],
        ["Approvals", summary.approvals],
        ["Overrides", summary.overrides],
        ["Review acknowledgments", summary.reviews],
      ] as const)
    : [];
  return (
    <div className="operational-page reports-page">
      <div className="page-notice">
        <Badge tone="purple">LOCAL DEMO REPORT</Badge>
        <p>
          This report summarizes only the available loaded records (up to 100),
          across facilities in the audit response. These are not all-time totals
          or real facility outcomes.
        </p>
        <p className="page-source">
          Source: GET /api/audit?limit=100 · Retrieved:{" "}
          {formatTime(resource.checkedAt)}
        </p>
      </div>
      {resource.status === "loading" && (
        <p role="status">
          Loading operational summary… Retained values, if shown, come from the
          previous audit read.
        </p>
      )}
      {resource.error && (
        <Card className="page-empty">
          <h2>Report unavailable</h2>
          <p role="alert">{resource.error}</p>
          <Button variant="outline" onClick={refresh}>
            Retry report
          </Button>
        </Card>
      )}
      {summary && (
        <>
          <div className="report-metrics">
            {metrics.map(([label, value]) => (
              <Card key={label} className="report-metric">
                <span>{label}</span>
                <strong>{value}</strong>
              </Card>
            ))}
          </div>
          {summary.total === 0 ? (
            <Card className="page-empty">
              <h2>No finalized decisions loaded</h2>
              <p>
                Create a demo evaluation and explicitly approve, override, or
                acknowledge review before a record appears here.
              </p>
              <Button onClick={onEvaluate}>Open Decision Queue</Button>
            </Card>
          ) : (
            <>
              <Card>
                <CardHeader>
                  <h2>Original versus final operating postures</h2>
                </CardHeader>
                <CardContent>
                  <div className="report-table-wrap">
                    <table className="report-table">
                      <caption>
                        Posture comparisons for loaded decisions
                      </caption>
                      <thead>
                        <tr>
                          <th>Original engine recommendation</th>
                          <th>Final human posture</th>
                          <th>Decisions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {summary.transitions.map((row) => (
                          <tr key={`${row.original}/${row.final}`}>
                            <td>{row.original}</td>
                            <td>{row.final}</td>
                            <td>{row.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p>
                    Review acknowledgments preserve no operating posture. An
                    override retains both the original recommendation and the
                    human choice.
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <h2>Employee impact & simulated preparation</h2>
                </CardHeader>
                <CardContent>
                  <p>
                    Counts belong to the selected decision’s saved notification
                    plan. They are not summed across decisions because the same
                    synthetic employees may appear repeatedly.
                  </p>
                  <p>
                    Only the selected record is retrieved. A missing or
                    unavailable plan supplies no employee counts.
                    GENERATED_SIMULATED means prepared messages; no delivery is
                    recorded.
                  </p>
                  <div className="page-select">
                    <label htmlFor="report-decision">
                      Decision for employee impact
                    </label>
                    <select
                      id="report-decision"
                      value={selected?.decision_id ?? ""}
                      onChange={(event) => setChosenId(event.target.value)}
                    >
                      {summary.decisions.map((d) => (
                        <option value={d.decision_id} key={d.decision_id}>
                          {d.manager_action} ·{" "}
                          {d.evidence_snapshot.facility.name} · {d.decision_id}
                        </option>
                      ))}
                    </select>
                  </div>
                </CardContent>
              </Card>
              {selected && (
                <DecisionInspection
                  key={selected.decision_id}
                  id={selected.decision_id}
                />
              )}
              <DecisionHistory
                resource={{ ...resource, data: summary.decisions }}
                refresh={refresh}
                title="Recent decision timeline"
                onInspect={onInspect}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}
