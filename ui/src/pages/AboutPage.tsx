import { useServiceInfo } from "@/api/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function AboutPage() {
  const { data } = useServiceInfo();
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">About</h1>
      <Card>
        <CardHeader><CardTitle>Server</CardTitle></CardHeader>
        <CardContent className="text-sm space-y-1">
          <p><span className="text-muted-foreground">Status:</span> {data?.status ?? "…"}</p>
          <p><span className="text-muted-foreground">Version:</span> {data?.version ?? "…"}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Wire up your snakemake run</CardTitle></CardHeader>
        <CardContent>
          <pre className="bg-muted/50 rounded-md p-4 text-xs overflow-x-auto">
{`pip install snakemake-logger-plugin-panoptes

snakemake \\
  --logger panoptes \\
  --logger-panoptes-url http://127.0.0.1:5050 \\
  --cores 2`}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}
