import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  useJobs, useRenameWorkflow, useWorkflow, useWorkflowDag, useWorkflowStats,
} from "@/api/hooks";
import { useWorkflowEvents } from "@/api/useWorkflowEvents";
import type { Job, JobStatus } from "@/api/types";
import { StatusBadge } from "@/components/StatusBadge";
import { JobsTable } from "@/components/JobsTable";
import { JobsFilters, type FilterState } from "@/components/JobsFilters";
import { RuleProgress } from "@/components/RuleProgress";
import { DurationChart } from "@/components/DurationChart";
import { DagView } from "@/components/DagView";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { fmtDuration, durationSeconds, relativeTime } from "@/lib/format";
import { ArrowLeft, Pencil, Radio } from "lucide-react";
import { cn } from "@/lib/utils";

function applyFilters(jobs: Job[], f: FilterState): Job[] {
  const needle = f.search.trim().toLowerCase();
  return jobs.filter((j) => {
    if (f.rule && j.rule !== f.rule) return false;
    if (f.status && j.status !== f.status) return false;
    if (needle) {
      const hay = `${j.rule} ${j.wildcards ?? ""}`.toLowerCase();
      if (!hay.includes(needle)) return false;
    }
    return true;
  });
}

export function WorkflowDetailPage() {
  const id = Number(useParams().id);
  const { data: wf } = useWorkflow(id);
  const { data: jobs = [] } = useJobs(id);
  const { data: stats } = useWorkflowStats(id);
  const { data: dag } = useWorkflowDag(id);
  const rename = useRenameWorkflow(id);
  const { connected } = useWorkflowEvents(id);
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();

  const filters: FilterState = {
    rule: searchParams.get("rule") ?? "",
    status: (searchParams.get("status") ?? "") as "" | JobStatus,
    search: searchParams.get("q") ?? "",
  };
  const setFilters = (next: FilterState) => {
    const sp = new URLSearchParams();
    if (next.rule) sp.set("rule", next.rule);
    if (next.status) sp.set("status", next.status);
    if (next.search) sp.set("q", next.search);
    setSearchParams(sp, { replace: true });
  };

  const filtered = useMemo(() => applyFilters(jobs, filters), [jobs, filters]);
  const failedJobs = useMemo(() => jobs.filter((j) => j.status === "error"), [jobs]);
  const ruleNames = useMemo(
    () => Array.from(new Set(jobs.map((j) => j.rule))).sort(),
    [jobs],
  );

  if (!wf) return <p className="text-muted-foreground">Loading…</p>;

  const totalJobs = stats?.total ?? wf.total_jobs ?? 0;
  const doneJobs = stats?.by_status.done ?? 0;
  const overallPct = totalJobs > 0 ? (doneJobs / totalJobs) * 100 : 0;
  const elapsed = durationSeconds(wf.started_at, wf.completed_at ?? new Date().toISOString());

  const startEdit = () => { setDraftName(wf.name ?? ""); setEditing(true); };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    rename.mutate(draftName, { onSuccess: () => setEditing(false) });
  };

  return (
    <div className="space-y-6">
      <div>
        <Link to="/workflows" className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
          <ArrowLeft className="h-3 w-3" /> Workflows
        </Link>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              {editing ? (
                <form onSubmit={submit} className="flex items-center gap-2">
                  <input autoFocus value={draftName}
                    onChange={(e) => setDraftName(e.target.value)}
                    className="bg-background border rounded-md px-2 py-1 text-lg font-semibold" />
                  <button type="submit" className="text-sm text-primary">save</button>
                  <button type="button" onClick={() => setEditing(false)} className="text-sm text-muted-foreground">cancel</button>
                </form>
              ) : (
                <CardTitle className="flex items-center gap-2">
                  {wf.name ?? wf.run_id.slice(0, 12)}
                  <button onClick={startEdit} className="text-muted-foreground hover:text-foreground">
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                </CardTitle>
              )}
              <p className="text-xs text-muted-foreground font-mono mt-1 truncate">{wf.run_id}</p>
            </div>
            <div className="flex items-center gap-2">
              <span
                title={connected ? "live updates connected" : "polling fallback"}
                className={cn(
                  "inline-flex items-center gap-1 text-xs",
                  connected ? "text-success" : "text-muted-foreground",
                )}
              >
                <Radio className={cn("h-3 w-3", connected && "animate-pulse")} />
                {connected ? "live" : "polling"}
              </span>
              <StatusBadge status={wf.status} />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div><dt className="text-muted-foreground">Snakemake</dt><dd className="font-mono">{wf.snakemake_version ?? "—"}</dd></div>
            <div><dt className="text-muted-foreground">Started</dt><dd>{relativeTime(wf.started_at)}</dd></div>
            <div><dt className="text-muted-foreground">{wf.completed_at ? "Elapsed" : "Running for"}</dt><dd>{fmtDuration(elapsed)}</dd></div>
            <div><dt className="text-muted-foreground">Working dir</dt><dd className="font-mono text-xs truncate">{wf.cwd ?? "—"}</dd></div>
          </dl>
          <div className="mt-6">
            <div className="flex items-baseline justify-between text-sm mb-2">
              <span className="font-medium">Overall progress</span>
              <span className="text-muted-foreground">{doneJobs} / {totalJobs}</span>
            </div>
            <Progress value={overallPct} />
          </div>
        </CardContent>
      </Card>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle>By rule</CardTitle></CardHeader>
          <CardContent><RuleProgress rules={stats?.by_rule ?? []} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Mean duration per rule</CardTitle></CardHeader>
          <CardContent><DurationChart rules={stats?.by_rule ?? []} /></CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Jobs</CardTitle></CardHeader>
        <CardContent>
          <Tabs defaultValue="all">
            <TabsList>
              <TabsTrigger value="all">All ({jobs.length})</TabsTrigger>
              <TabsTrigger value="failed">Failed ({failedJobs.length})</TabsTrigger>
              <TabsTrigger value="dag" disabled={!dag}>DAG</TabsTrigger>
            </TabsList>
            <TabsContent value="all">
              <JobsFilters
                rules={ruleNames}
                value={filters}
                onChange={setFilters}
              />
              <JobsTable workflowId={id} jobs={filtered} />
            </TabsContent>
            <TabsContent value="failed">
              <JobsTable workflowId={id} jobs={failedJobs} />
            </TabsContent>
            <TabsContent value="dag">
              {dag && (
                <DagView
                  dag={dag}
                  rules={stats?.by_rule ?? []}
                  onSelectRule={(rule) => setFilters({ ...filters, rule: rule ?? "" })}
                />
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
