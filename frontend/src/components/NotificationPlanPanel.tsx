import type { NotificationPlan } from "../api/schemas";
import { formatTime } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader } from "./ui/card";

export function NotificationPlanPanel({ plan }: { plan: NotificationPlan }) {
  const counts = [
    ["Assigned", plan.total_assigned],
    ["Scheduled", plan.total_scheduled],
    ["Telework eligible", plan.group_counts.TELEWORK_ELIGIBLE],
    ["Standard onsite", plan.group_counts.STANDARD_ONSITE],
    ["Essential", plan.group_counts.ESSENTIAL_PERSONNEL],
    ["Excluded", plan.total_unscheduled],
  ] as const;
  return (
    <Card className="notification-plan">
      <CardHeader>
        <h2>Employee impact & notification plan</h2>
      </CardHeader>
      <CardContent>
        <Badge tone="purple">SIMULATED DEMO</Badge> <Badge>{plan.status}</Badge>
        <p>
          <strong>No real notifications sent</strong>
        </p>
        <p className="record-id">Plan ID: {plan.notification_plan_id}</p>
        <p className="record-id">Decision ID: {plan.decision_id}</p>
        <div className="impact-counts">
          {counts.map(([label, count]) => (
            <div key={label}>
              <strong>{count}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
        <p>
          Final manager posture: {plan.final_posture}. Effective time: not
          recorded.
        </p>
        {plan.messages.map((message) => (
          <details className="message-preview" key={message.group}>
            <summary>
              {message.group.replaceAll("_", " ")} · {message.count} ·{" "}
              {message.status}
            </summary>
            <p>{message.message}</p>
            <small>Route: {message.route}</small>
          </details>
        ))}
        <p className="source-note">
          Source: {plan.roster_source} ·{" "}
          {formatTime(plan.roster_source_timestamp)}
          <br />
          Prepared: {formatTime(plan.created_at)}
        </p>
      </CardContent>
    </Card>
  );
}
