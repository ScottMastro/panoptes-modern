import { X } from "lucide-react";
import type { JobStatus } from "@/api/types";
import { cn } from "@/lib/utils";

const STATUS_OPTIONS: { value: "" | JobStatus; label: string }[] = [
  { value: "", label: "Any status" },
  { value: "done", label: "Done" },
  { value: "running", label: "Running" },
  { value: "pending", label: "Pending" },
  { value: "error", label: "Error" },
];

const inputCls =
  "h-9 rounded-md border bg-background px-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

export interface FilterState {
  rule: string;
  status: "" | JobStatus;
  search: string;
}

export function JobsFilters({
  rules, value, onChange,
}: {
  rules: string[];
  value: FilterState;
  onChange: (next: FilterState) => void;
}) {
  const hasFilters = value.rule || value.status || value.search;

  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <select
        className={cn(inputCls, "min-w-[140px]")}
        value={value.rule}
        onChange={(e) => onChange({ ...value, rule: e.target.value })}
      >
        <option value="">All rules</option>
        {rules.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <select
        className={cn(inputCls, "min-w-[140px]")}
        value={value.status}
        onChange={(e) =>
          onChange({ ...value, status: e.target.value as FilterState["status"] })
        }
      >
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <input
        type="search"
        placeholder="Search rule or wildcards…"
        className={cn(inputCls, "flex-1 min-w-[180px]")}
        value={value.search}
        onChange={(e) => onChange({ ...value, search: e.target.value })}
      />
      {hasFilters && (
        <button
          onClick={() => onChange({ rule: "", status: "", search: "" })}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2"
        >
          <X className="h-3 w-3" /> Clear
        </button>
      )}
    </div>
  );
}
