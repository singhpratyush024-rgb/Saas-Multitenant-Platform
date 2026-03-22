// lib/api/tasks.ts

import api from "@/lib/axios";

export interface Task {
  id: number;
  title: string;
  description?: string;
  status: "todo" | "in_progress" | "done";
  project_id: number;
  assigned_to?: number;
  tenant_id: number;
  created_at: string;
}

// Fetch tasks for a specific project
export async function getTasks(projectId: number): Promise<Task[]> {
  const res = await api.get<any>(`/projects/${projectId}/tasks/`);
  const d = res.data;
  return Array.isArray(d) ? d : d?.data ?? d?.items ?? [];
}

// Fetch tasks across all projects
export async function getAllTasks(projectIds: number[]): Promise<Task[]> {
  if (projectIds.length === 0) return [];
  const results = await Promise.all(projectIds.map((id) => getTasks(id)));
  return results.flat();
}

export async function createTask(data: {
  title: string;
  description?: string;
  project_id: number;
  status?: string;
}): Promise<Task> {
  const res = await api.post<any>(
    `/projects/${data.project_id}/tasks/`,
    {
      title: data.title,
      description: data.description,
      status: data.status ?? "todo",
    }
  );
  const d = res.data;
  return d?.data ?? d;
}

export async function updateTask(
  projectId: number,
  taskId: number,
  data: { title?: string; status?: string; description?: string }
): Promise<Task> {
  const res = await api.patch<any>(
    `/projects/${projectId}/tasks/${taskId}`,
    data
  );
  const d = res.data;
  return d?.data ?? d;
}

export async function deleteTask(
  projectId: number,
  taskId: number
): Promise<void> {
  await api.delete(`/projects/${projectId}/tasks/${taskId}`);
}