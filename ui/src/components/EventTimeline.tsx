import type { JobEvent } from "@/api/types";

export function EventTimeline({ events }: { events: JobEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">No events recorded.</p>;
  }
  return (
    <ol className="space-y-3 relative border-l border-border ml-2">
      {events.map((e) => (
        <li key={e.id} className="ml-4">
          <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-success" />
          <time className="text-xs text-muted-foreground tabular-nums">
            {new Date(e.timestamp).toLocaleTimeString()}
          </time>
          <p className="text-sm font-medium">{e.event}</p>
          {e.detail && (
            <pre className="mt-1 text-xs text-muted-foreground bg-muted/40 rounded p-2 overflow-x-auto">
              {e.detail}
            </pre>
          )}
        </li>
      ))}
    </ol>
  );
}
