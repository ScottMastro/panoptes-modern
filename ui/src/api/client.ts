const BASE = (import.meta.env.VITE_API_BASE ?? "") + "/api/v1";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) msg = body.detail;
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

import type {
  Job, JobEvent, JobLog, ServiceInfo, Workflow, WorkflowDag, WorkflowStats,
} from "./types";

export const api = {
  serviceInfo: () => req<ServiceInfo>("/service-info"),
  workflows: () => req<Workflow[]>("/workflows"),
  workflow: (id: number) => req<Workflow>(`/workflows/${id}`),
  jobs: (id: number) => req<Job[]>(`/workflows/${id}/jobs`),
  job: (wfId: number, jobId: number) =>
    req<Job>(`/workflows/${wfId}/jobs/${jobId}`),
  jobEvents: (wfId: number, jobId: number) =>
    req<JobEvent[]>(`/workflows/${wfId}/jobs/${jobId}/events`),
  stats: (id: number) => req<WorkflowStats>(`/workflows/${id}/stats`),
  dag: (id: number) => req<WorkflowDag>(`/workflows/${id}/dag`),
  jobLog: (wfId: number, jobId: number, lines = 200) =>
    req<JobLog>(`/workflows/${wfId}/jobs/${jobId}/log?lines=${lines}`),
  rename: (id: number, name: string) =>
    req<Workflow>(`/workflows/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    }),
  deleteWorkflow: (id: number) =>
    req<void>(`/workflows/${id}`, { method: "DELETE" }),
};
