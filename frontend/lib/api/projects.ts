// lib/api/projects.ts

import api from "@/lib/axios";

export interface Project {
  id: number;
  name: string;
  description?: string;
  tenant_id: number;
  created_at: string;
  updated_at?: string;
}

export interface ProjectsResponse {
  data: Project[];
  total?: number;
}

export async function getProjects(): Promise<Project[]> {
  const res = await api.get<ProjectsResponse>("/projects/");
  // Handle both array and paginated envelope
  const d = res.data as any;
  return Array.isArray(d) ? d : d?.data ?? d?.items ?? [];
}

export async function createProject(data: {
  name: string;
  description?: string;
}): Promise<Project> {
  const res = await api.post<{ data: Project } | Project>("/projects/", data);
  const d = res.data as any;
  return d?.data ?? d;
}

export async function updateProject(
  id: number,
  data: { name?: string; description?: string }
): Promise<Project> {
  const res = await api.patch<{ data: Project } | Project>(`/projects/${id}`, data);
  const d = res.data as any;
  return d?.data ?? d;
}

export async function deleteProject(id: number): Promise<void> {
  await api.delete(`/projects/${id}`);
}