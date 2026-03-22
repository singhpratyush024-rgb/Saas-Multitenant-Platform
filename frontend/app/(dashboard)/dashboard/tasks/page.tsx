"use client";
// app/(dashboard)/dashboard/tasks/page.tsx

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getAllTasks,
  createTask,
  deleteTask,
  updateTask,
  type Task,
} from "@/lib/api/tasks";
import { getProjects } from "@/lib/api/projects";
import { getMembers } from "@/lib/api/members";
import { useRole } from "@/hooks/use-role";
import { useToast } from "@/hooks/use-toast";
import { SearchInput } from "@/components/ui/search-input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  CheckSquare,
  Plus,
  Trash2,
  Loader2,
  Circle,
  CheckCircle2,
  Clock,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const PAGE_SIZE = 15;

const STATUS_CONFIG = {
  todo: { label: "To do", icon: Circle, class: "text-muted-foreground" },
  in_progress: { label: "In progress", icon: Clock, class: "text-yellow-500" },
  done: { label: "Done", icon: CheckCircle2, class: "text-green-500" },
};

function EmptyState({ hasProjects, filtered }: { hasProjects: boolean; filtered: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mb-4">
        <CheckSquare className="w-8 h-8 text-muted-foreground" />
      </div>
      <h3 className="font-semibold text-foreground mb-1">
        {filtered ? "No matching tasks" : "No tasks yet"}
      </h3>
      <p className="text-sm text-muted-foreground max-w-xs">
        {filtered
          ? "Try adjusting your search or filter."
          : hasProjects
          ? "Create your first task to start tracking work."
          : "Create a project first, then add tasks."}
      </p>
    </div>
  );
}

export default function TasksPage() {
  const { can } = useRole();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [projectFilter, setProjectFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [form, setForm] = useState({
    title: "",
    description: "",
    project_id: "",
    status: "todo",
    assigned_to: "",
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: getProjects,
  });

  const { data: membersData } = useQuery({
    queryKey: ["members"],
    queryFn: () => getMembers(1, 100),
  });
  const members = membersData?.items ?? [];

  const { data: allTasks = [], isLoading } = useQuery({
    queryKey: ["tasks", projects.map((p) => p.id)],
    queryFn: () => getAllTasks(projects.map((p) => p.id)),
    enabled: projects.length > 0,
  });

  // Filter + search
  const filtered = useMemo(() => {
    return allTasks.filter((t) => {
      const matchSearch = t.title.toLowerCase().includes(search.toLowerCase());
      const matchStatus = statusFilter === "all" || t.status === statusFilter;
      const matchProject = projectFilter === "all" || t.project_id === Number(projectFilter);
      return matchSearch && matchStatus && matchProject;
    });
  }, [allTasks, search, statusFilter, projectFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const counts = useMemo(() => ({
    all: allTasks.length,
    todo: allTasks.filter((t) => t.status === "todo").length,
    in_progress: allTasks.filter((t) => t.status === "in_progress").length,
    done: allTasks.filter((t) => t.status === "done").length,
  }), [allTasks]);

  const createMutation = useMutation({
    mutationFn: createTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setOpen(false);
      setForm({ title: "", description: "", project_id: "", status: "todo", assigned_to: "" });
      toast({ title: "Task created" });
    },
    onError: (e: any) =>
      toast({ variant: "destructive", title: "Failed", description: e?.response?.data?.detail }),
  });

  const deleteMutation = useMutation({
    mutationFn: ({ projectId, taskId }: { projectId: number; taskId: number }) =>
      deleteTask(projectId, taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setDeleteTarget(null);
      toast({ title: "Task deleted" });
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ projectId, taskId, status }: { projectId: number; taskId: number; status: string }) =>
      updateTask(projectId, taskId, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });

  return (
    <div className="space-y-6 animate-fade-in" style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ letterSpacing: "-0.025em" }}>Tasks</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {filtered.length} task{filtered.length !== 1 ? "s" : ""}
            {search && ` matching "${search}"`}
          </p>
        </div>
        {can.createProject && projects.length > 0 && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="gap-2">
                <Plus className="w-4 h-4" />
                New task
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Create task</DialogTitle></DialogHeader>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!form.project_id) return;
                  createMutation.mutate({
                    title: form.title,
                    description: form.description,
                    project_id: Number(form.project_id),
                    status: form.status,
                  });
                }}
                className="space-y-4 mt-2"
              >
                <div className="space-y-2">
                  <Label>Project</Label>
                  <select
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={form.project_id}
                    onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                    required disabled={createMutation.isPending}
                  >
                    <option value="">Select project…</option>
                    {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label>Title</Label>
                  <Input
                    placeholder="Task title"
                    value={form.title}
                    onChange={(e) => setForm({ ...form, title: e.target.value })}
                    required disabled={createMutation.isPending}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label>Status</Label>
                    <select
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                      value={form.status}
                      onChange={(e) => setForm({ ...form, status: e.target.value })}
                      disabled={createMutation.isPending}
                    >
                      <option value="todo">To do</option>
                      <option value="in_progress">In progress</option>
                      <option value="done">Done</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label>Assign to</Label>
                    <select
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                      value={form.assigned_to}
                      onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}
                      disabled={createMutation.isPending}
                    >
                      <option value="">Unassigned</option>
                      {members.map((m) => <option key={m.id} value={m.id}>{m.email}</option>)}
                    </select>
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                  <Button type="submit" disabled={createMutation.isPending}>
                    {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create"}
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput
          value={search}
          onChange={(v) => { setSearch(v); setPage(1); }}
          placeholder="Search tasks…"
          className="w-56"
        />

        {/* Status tabs */}
        <div className="flex gap-1 bg-muted p-1 rounded-lg">
          {(["all", "todo", "in_progress", "done"] as const).map((s) => (
            <button
              key={s}
              onClick={() => { setStatusFilter(s); setPage(1); }}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${
                statusFilter === s
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {s === "all" ? `All (${counts.all})` : `${STATUS_CONFIG[s].label} (${counts[s]})`}
            </button>
          ))}
        </div>

        {/* Project filter */}
        {projects.length > 1 && (
          <select
            className="h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={projectFilter}
            onChange={(e) => { setProjectFilter(e.target.value); setPage(1); }}
          >
            <option value="all">All projects</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        )}
      </div>

      {/* Task list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : paginated.length === 0 ? (
        <EmptyState hasProjects={projects.length > 0} filtered={!!search || statusFilter !== "all" || projectFilter !== "all"} />
      ) : (
        <div className="bg-card border border-border rounded-2xl overflow-hidden">
          {paginated.map((task, i) => {
            const s = STATUS_CONFIG[task.status] ?? STATUS_CONFIG.todo;
            const Icon = s.icon;
            const project = projects.find((p) => p.id === task.project_id);
            const assignee = members.find((m) => m.id === task.assigned_to);

            return (
              <div
                key={task.id}
                className={`flex items-center gap-3 px-5 py-3.5 group ${
                  i !== paginated.length - 1 ? "border-b border-border" : ""
                }`}
              >
                <button
                  onClick={() => {
                    const next = task.status === "todo" ? "in_progress" : task.status === "in_progress" ? "done" : "todo";
                    statusMutation.mutate({ projectId: task.project_id, taskId: task.id, status: next });
                  }}
                  className="shrink-0"
                >
                  <Icon className={`w-4 h-4 ${s.class}`} />
                </button>

                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${task.status === "done" ? "line-through text-muted-foreground" : "text-foreground"}`}>
                    {task.title}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    {project && <span className="text-xs text-muted-foreground">{project.name}</span>}
                    {project && assignee && <span className="text-xs text-muted-foreground">·</span>}
                    {assignee && (
                      <span className="text-xs text-muted-foreground">
                        {assignee.email.split("@")[0]}
                      </span>
                    )}
                  </div>
                </div>

                <span className={`text-xs font-medium px-2 py-0.5 rounded-full hidden sm:inline-block ${
                  task.status === "done"
                    ? "bg-green-100 text-green-700"
                    : task.status === "in_progress"
                    ? "bg-yellow-100 text-yellow-700"
                    : "bg-muted text-muted-foreground"
                }`}>
                  {s.label}
                </span>

                {can.deleteProject && (
                  <button
                    onClick={() => setDeleteTarget(task)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages} · {filtered.length} tasks
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Delete task"
        description={`Delete "${deleteTarget?.title}"? This cannot be undone.`}
        confirmLabel="Delete"
        destructive
        loading={deleteMutation.isPending}
        onConfirm={() =>
          deleteTarget && deleteMutation.mutate({ projectId: deleteTarget.project_id, taskId: deleteTarget.id })
        }
      />
    </div>
  );
}