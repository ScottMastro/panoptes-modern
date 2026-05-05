import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { WorkflowsPage } from "@/pages/WorkflowsPage";
import { WorkflowDetailPage } from "@/pages/WorkflowDetailPage";
import { JobDetailPage } from "@/pages/JobDetailPage";
import { AboutPage } from "@/pages/AboutPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/workflows" replace />} />
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
        <Route path="/workflows/:id/jobs/:jobId" element={<JobDetailPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/workflows" replace />} />
      </Route>
    </Routes>
  );
}
