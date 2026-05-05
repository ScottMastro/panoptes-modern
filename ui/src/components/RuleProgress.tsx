import type { RuleStat } from "@/api/types";
import { Progress } from "@/components/ui/progress";

export function RuleProgress({ rules }: { rules: RuleStat[] }) {
  if (rules.length === 0) {
    return <p className="text-sm text-muted-foreground">No rules yet.</p>;
  }
  return (
    <div className="space-y-3">
      {rules.map((r) => {
        const pct = r.total > 0 ? (r.done / r.total) * 100 : 0;
        return (
          <div key={r.rule}>
            <div className="flex items-baseline justify-between text-sm">
              <span className="font-mono">{r.rule}</span>
              <span className="text-muted-foreground">
                {r.done} / {r.total}
                {r.error > 0 && (
                  <span className="ml-2 text-destructive">{r.error} failed</span>
                )}
              </span>
            </div>
            <Progress value={pct} className="mt-1" />
          </div>
        );
      })}
    </div>
  );
}
