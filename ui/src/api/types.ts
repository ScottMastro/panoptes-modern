export type WorkflowStatus = "running" | "done" | "error" | "no_execution";
export type JobStatus = "pending" | "running" | "done" | "error";

export interface Workflow {
  id: number;
  run_id: string;
  name: string | null;
  status: WorkflowStatus;
  started_at: string;
  completed_at: string | null;
  total_jobs: number | null;
  snakemake_version: string | null;
  cwd: string | null;
  snakefile: string | null;
}

export interface Job {
  id: number;
  workflow_id: number;
  internal_id: number;
  rule: string;
  wildcards: string | null;
  status: JobStatus;
  started_at: string | null;
  finished_at: string | null;
  threads: number | null;
  log_path: string | null;
}

export interface JobEvent {
  id: number;
  timestamp: string;
  event: string;
  detail: string | null;
}

export interface RuleStat {
  rule: string;
  total: number;
  done: number;
  running: number;
  pending: number;
  error: number;
  mean_duration_seconds: number | null;
}

export interface WorkflowStats {
  total: number;
  by_status: Record<JobStatus, number>;
  by_rule: RuleStat[];
}

export interface ServiceInfo {
  status: string;
  version: string;
}

export interface DagNode { rule: string; }
export interface DagEdge { source: number; target: number; }
export interface WorkflowDag {
  nodes: DagNode[];
  edges: DagEdge[];
  captured_at: string;
}

export interface JobLog {
  path: string;
  lines: string[];
  truncated: boolean;
  size_bytes: number;
}
