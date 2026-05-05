import { useState } from "react";
import { useJobLog } from "@/api/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText } from "lucide-react";

export function LogTail({ wfId, jobId }: { wfId: number; jobId: number }) {
  const [lines, setLines] = useState(200);
  const { data, error, isLoading } = useJobLog(wfId, jobId, lines);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4" /> Log
          </CardTitle>
          {data?.truncated && (
            <Badge variant="secondary">truncated · last {lines} lines</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && (
          <p className="text-sm text-muted-foreground">
            No log available: {(error as Error).message}
          </p>
        )}
        {data && (
          <>
            {data.path && (
              <p className="text-xs text-muted-foreground font-mono mb-2 break-all">
                {data.path}
              </p>
            )}
            {data.lines.length === 0 ? (
              <p className="text-sm text-muted-foreground">Log is empty.</p>
            ) : (
              <pre className="bg-muted/40 rounded-md p-3 text-xs overflow-x-auto max-h-96 overflow-y-auto leading-relaxed">
                {data.lines.join("\n")}
              </pre>
            )}
            {data.truncated && lines < 1000 && (
              <button
                onClick={() => setLines(1000)}
                className="mt-3 text-xs text-primary hover:underline"
              >
                Show last 1000 lines
              </button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
