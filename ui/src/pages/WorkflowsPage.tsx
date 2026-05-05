import { Link } from "react-router-dom";
import { useWorkflows } from "@/api/hooks";
import { StatusBadge } from "@/components/StatusBadge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { relativeTime } from "@/lib/format";
import { ChevronRight } from "lucide-react";

export function WorkflowsPage() {
  const { data, isLoading, error } = useWorkflows();

  if (isLoading) return <p className="text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-destructive">{(error as Error).message}</p>;
  const workflows = data ?? [];

  if (workflows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>No runs yet</CardTitle>
          <CardDescription>
            Point a snakemake invocation at this server to start collecting events.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="bg-muted/50 rounded-md p-4 text-xs overflow-x-auto">
{`snakemake \\
  --logger panoptes \\
  --logger-panoptes-url http://127.0.0.1:5050 \\
  --cores 2`}
          </pre>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <h1 className="text-2xl font-semibold mb-6">Workflows</h1>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-muted-foreground text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Run</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Started</th>
              <th className="px-3 py-2 font-medium">Progress</th>
              <th className="px-3 py-2 font-medium">Snakefile</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {workflows.map((wf) => (
              <tr key={wf.id} className="border-t hover:bg-muted/30">
                <td className="px-3 py-2 font-medium">
                  <Link to={`/workflows/${wf.id}`} className="hover:underline">
                    {wf.name ?? wf.run_id.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-3 py-2"><StatusBadge status={wf.status} /></td>
                <td className="px-3 py-2 text-muted-foreground">
                  {relativeTime(wf.started_at)}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {wf.total_jobs ? `${wf.total_jobs} jobs` : "—"}
                </td>
                <td className="px-3 py-2 text-muted-foreground font-mono text-xs">
                  {wf.snakefile ? wf.snakefile.split("/").pop() : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  <Link to={`/workflows/${wf.id}`} className="text-muted-foreground hover:text-foreground">
                    <ChevronRight className="h-4 w-4 inline" />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
