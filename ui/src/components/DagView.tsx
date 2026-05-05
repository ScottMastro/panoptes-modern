import { useMemo } from "react";
import ReactFlow, {
  Background, Controls, type Edge, type Node, type NodeProps,
  Handle, Position,
} from "reactflow";
import dagre from "dagre";
import "reactflow/dist/style.css";
import type { RuleStat, WorkflowDag } from "@/api/types";
import { cn } from "@/lib/utils";

const NODE_W = 160;
const NODE_H = 44;

function colorForRule(stat: RuleStat | undefined) {
  if (!stat || stat.total === 0) return "muted";
  if (stat.error > 0) return "error";
  if (stat.running > 0) return "running";
  if (stat.done === stat.total) return "done";
  return "pending";
}

// Tinted backgrounds with a saturated border carry the status signal
// without blinding the user. Foreground stays the regular text color so
// it reads well in both light and dark modes.
const NODE_STYLES: Record<string, string> = {
  done: "bg-success/15 text-foreground border-success",
  running: "bg-primary/15 text-foreground border-primary",
  error: "bg-destructive/20 text-foreground border-destructive",
  pending: "bg-muted/40 text-muted-foreground border-border",
  muted: "bg-card text-muted-foreground border-border",
};

function RuleNode({ data, selected }: NodeProps) {
  const status = data.status as string;
  return (
    <div
      title={data.tooltip}
      className={cn(
        "rounded-md border-2 px-3 py-2 text-xs font-mono text-center transition shadow-sm",
        NODE_STYLES[status] ?? NODE_STYLES.muted,
        selected && "ring-2 ring-ring",
      )}
      style={{ width: NODE_W, height: NODE_H }}
    >
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <div className="truncate">{data.label}</div>
      {data.subLabel && (
        <div className="text-[10px] opacity-80">{data.subLabel}</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </div>
  );
}

const NODE_TYPES = { rule: RuleNode };

function layout(dag: WorkflowDag, statsByRule: Record<string, RuleStat>): {
  nodes: Node[]; edges: Edge[];
} {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 30, ranksep: 50 });
  g.setDefaultEdgeLabel(() => ({}));

  dag.nodes.forEach((n, i) => {
    g.setNode(String(i), { width: NODE_W, height: NODE_H, rule: n.rule });
  });
  dag.edges.forEach((e) => {
    g.setEdge(String(e.source), String(e.target));
  });
  dagre.layout(g);

  const nodes: Node[] = dag.nodes.map((n, i) => {
    const pos = g.node(String(i));
    const stat = statsByRule[n.rule];
    const status = colorForRule(stat);
    const sub = stat
      ? `${stat.done}/${stat.total}${stat.error ? ` · ${stat.error} err` : ""}`
      : "—";
    return {
      id: String(i),
      type: "rule",
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      data: {
        label: n.rule,
        subLabel: sub,
        status,
        tooltip: stat
          ? `${n.rule}: ${stat.done}/${stat.total} done${
              stat.mean_duration_seconds != null
                ? `, mean ${stat.mean_duration_seconds.toFixed(1)}s` : ""
            }`
          : n.rule,
      },
    };
  });

  const edges: Edge[] = dag.edges.map((e, idx) => ({
    id: `e${idx}`,
    source: String(e.source),
    target: String(e.target),
    type: "smoothstep",
    animated: false,
    style: { stroke: "hsl(var(--muted-foreground))", strokeWidth: 1.5 },
  }));

  return { nodes, edges };
}

export function DagView({
  dag, rules, onSelectRule,
}: {
  dag: WorkflowDag;
  rules: RuleStat[];
  onSelectRule: (rule: string | null) => void;
}) {
  const statsByRule = useMemo(
    () => Object.fromEntries(rules.map((r) => [r.rule, r])),
    [rules],
  );
  const { nodes, edges } = useMemo(
    () => layout(dag, statsByRule),
    [dag, statsByRule],
  );

  return (
    <div className="h-[480px] rounded-md border bg-card/30">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodeClick={(_e, n) => onSelectRule((n.data as { label: string }).label)}
        onPaneClick={() => onSelectRule(null)}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} color="hsl(var(--border))" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
