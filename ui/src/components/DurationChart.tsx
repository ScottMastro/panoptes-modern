import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { RuleStat } from "@/api/types";
import { fmtDuration } from "@/lib/format";

export function DurationChart({ rules }: { rules: RuleStat[] }) {
  const data = rules
    .filter((r) => r.mean_duration_seconds != null)
    .map((r) => ({ rule: r.rule, mean: r.mean_duration_seconds! }));

  if (data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No finished jobs yet.
      </p>
    );
  }
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey="rule" stroke="hsl(var(--muted-foreground))" fontSize={12} />
          <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12}
                 tickFormatter={(v) => fmtDuration(v)} />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8, fontSize: 12,
            }}
            formatter={(v: number) => [fmtDuration(v), "mean"]}
          />
          <Bar dataKey="mean" fill="hsl(var(--success))" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
