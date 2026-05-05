import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 10_000;

function wsUrl(workflowId: number): string {
  // Same-origin WS: derive from window.location so the dev server
  // (vite proxy) and prod (FastAPI) both work without extra config.
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/v1/ws/${workflowId}`;
}

/**
 * Subscribe to live updates for a workflow. Every server-side event
 * batch (i.e. every committed POST /ingest) triggers an immediate
 * invalidation of the workflow/jobs/stats query keys for this id, so
 * TanStack Query refetches and the UI updates without waiting for
 * the next polling tick.
 *
 * Polling stays on as a safety net — if the WS is closed (e.g.
 * proxy timeout), the user still sees state within ~2s.
 */
export function useWorkflowEvents(workflowId: number) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  // Track in a ref so we can resume reconnection across renders.
  const attemptRef = useRef(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      ws = new WebSocket(wsUrl(workflowId));

      ws.onopen = () => {
        attemptRef.current = 0;
        setConnected(true);
      };

      ws.onmessage = (e) => {
        let payload: { type?: string } = {};
        try { payload = JSON.parse(e.data); } catch { return; }
        // hello + ping carry no state. Any other message means
        // "something changed for this workflow" → invalidate.
        if (payload.type === "hello" || payload.type === "ping") return;
        qc.invalidateQueries({ queryKey: ["workflow", workflowId] });
        qc.invalidateQueries({ queryKey: ["jobs", workflowId] });
        qc.invalidateQueries({ queryKey: ["workflow-stats", workflowId] });
        // workflows-list page may also be open; refresh it cheaply.
        qc.invalidateQueries({ queryKey: ["workflows"] });
      };

      ws.onclose = (ev) => {
        setConnected(false);
        // 4404 = workflow not found; don't reconnect forever.
        if (ev.code === 4404 || cancelled) return;
        const delay = Math.min(
          RECONNECT_BASE_MS * 2 ** attemptRef.current,
          RECONNECT_MAX_MS,
        );
        attemptRef.current += 1;
        timer = window.setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // onclose will fire next; no extra action needed.
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
      if (ws && ws.readyState <= 1) ws.close();
    };
  }, [workflowId, qc]);

  return { connected };
}
