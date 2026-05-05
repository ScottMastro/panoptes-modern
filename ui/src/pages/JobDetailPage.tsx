import { Link, useParams } from "react-router-dom";
import { useJob, useJobEvents } from "@/api/hooks";
import { StatusBadge } from "@/components/StatusBadge";
import { EventTimeline } from "@/components/EventTimeline";
import { LogTail } from "@/components/LogTail";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft } from "lucide-react";
import { durationSeconds, fmtDuration, fmtWildcards } from "@/lib/format";

export function JobDetailPage() {
  const wfId = Number(useParams().id);
  const jobId = Number(useParams().jobId);
  const { data: job } = useJob(wfId, jobId);
  const { data: events = [] } = useJobEvents(wfId, jobId);

  if (!job) return <p className="text-muted-foreground">Loading…</p>;
  const dur = durationSeconds(job.started_at, job.finished_at);

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/workflows/${wfId}`} className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
          <ArrowLeft className="h-3 w-3" /> Workflow
        </Link>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="font-mono">{job.rule}</CardTitle>
              <p className="text-xs text-muted-foreground mt-1">internal id: {job.internal_id}</p>
            </div>
            <StatusBadge status={job.status} />
          </div>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
            <div>
              <dt className="text-muted-foreground">Wildcards</dt>
              <dd className="font-mono text-xs">{fmtWildcards(job.wildcards)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Threads</dt>
              <dd>{job.threads ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Duration</dt>
              <dd>{fmtDuration(dur)}</dd>
            </div>
            {job.log_path && (
              <div className="col-span-full">
                <dt className="text-muted-foreground">Log</dt>
                <dd className="font-mono text-xs break-all">{job.log_path}</dd>
              </div>
            )}
          </dl>
        </CardContent>
      </Card>

      {job.log_path && (job.status === "done" || job.status === "error") && (
        <LogTail wfId={wfId} jobId={jobId} />
      )}

      <Card>
        <CardHeader><CardTitle>Timeline</CardTitle></CardHeader>
        <CardContent><EventTimeline events={events} /></CardContent>
      </Card>
    </div>
  );
}
