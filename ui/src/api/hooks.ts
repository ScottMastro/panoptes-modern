import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

const POLL_RUNNING = 2000;

export const useServiceInfo = () =>
  useQuery({ queryKey: ["service-info"], queryFn: api.serviceInfo });

export const useWorkflows = () =>
  useQuery({
    queryKey: ["workflows"],
    queryFn: api.workflows,
    refetchInterval: POLL_RUNNING,
  });

export const useWorkflow = (id: number) =>
  useQuery({
    queryKey: ["workflow", id],
    queryFn: () => api.workflow(id),
    refetchInterval: (q) =>
      q.state.data?.status === "running" ? POLL_RUNNING : false,
  });

export const useJobs = (id: number, status?: string) =>
  useQuery({
    queryKey: ["jobs", id],
    queryFn: () => api.jobs(id),
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return POLL_RUNNING;
      const anyActive = data.some((j) => j.status === "running" || j.status === "pending");
      return anyActive ? POLL_RUNNING : false;
    },
    select: status ? (rows) => rows.filter((r) => r.status === status) : undefined,
  });

export const useJob = (wfId: number, jobId: number) =>
  useQuery({
    queryKey: ["job", wfId, jobId],
    queryFn: () => api.job(wfId, jobId),
    refetchInterval: (q) =>
      q.state.data?.status === "running" || q.state.data?.status === "pending"
        ? POLL_RUNNING : false,
  });

export const useJobEvents = (wfId: number, jobId: number) =>
  useQuery({
    queryKey: ["job-events", wfId, jobId],
    queryFn: () => api.jobEvents(wfId, jobId),
    refetchInterval: POLL_RUNNING,
  });

export const useWorkflowStats = (id: number) =>
  useQuery({
    queryKey: ["workflow-stats", id],
    queryFn: () => api.stats(id),
    refetchInterval: POLL_RUNNING,
  });

export const useWorkflowDag = (id: number) =>
  useQuery({
    queryKey: ["workflow-dag", id],
    queryFn: () => api.dag(id),
    retry: false,
    // DAG topology is captured once; no need to repoll.
    staleTime: Infinity,
  });

export const useJobLog = (wfId: number, jobId: number, lines = 200) =>
  useQuery({
    queryKey: ["job-log", wfId, jobId, lines],
    queryFn: () => api.jobLog(wfId, jobId, lines),
    retry: false,
  });

export const useRenameWorkflow = (id: number) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.rename(id, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow", id] });
      qc.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
};
