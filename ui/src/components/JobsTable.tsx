import { Link } from "react-router-dom";
import type { Job } from "@/api/types";
import { StatusBadge } from "./StatusBadge";
import { durationSeconds, fmtDuration, fmtWildcards } from "@/lib/format";

export function JobsTable({ workflowId, jobs }: { workflowId: number; jobs: Job[] }) {
  if (jobs.length === 0) {
    return <p className="text-sm text-muted-foreground py-8 text-center">No jobs yet.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-muted-foreground text-left">
          <tr>
            <th className="px-3 py-2 font-medium">#</th>
            <th className="px-3 py-2 font-medium">Rule</th>
            <th className="px-3 py-2 font-medium">Wildcards</th>
            <th className="px-3 py-2 font-medium">Threads</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="px-3 py-2 font-medium">Duration</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => {
            const dur = durationSeconds(j.started_at, j.finished_at);
            return (
              <tr key={j.id} className="border-t hover:bg-muted/30">
                <td className="px-3 py-2 text-muted-foreground">{j.internal_id}</td>
                <td className="px-3 py-2 font-mono">
                  <Link
                    to={`/workflows/${workflowId}/jobs/${j.id}`}
                    className="hover:underline"
                  >
                    {j.rule}
                  </Link>
                </td>
                <td className="px-3 py-2 text-muted-foreground">{fmtWildcards(j.wildcards)}</td>
                <td className="px-3 py-2 text-muted-foreground">{j.threads ?? "—"}</td>
                <td className="px-3 py-2"><StatusBadge status={j.status} /></td>
                <td className="px-3 py-2 text-muted-foreground">{fmtDuration(dur)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
