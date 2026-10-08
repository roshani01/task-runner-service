import { Stats, Task } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return resp.json();
}

export const api = {
  listTasks: () => request<Task[]>("/tasks"),
  getTask: (id: string) => request<Task>(`/tasks/${id}`),
  cancelTask: (id: string) =>
    request<{ task_id: string; status: string }>(`/tasks/${id}/cancel`, { method: "POST" }),
  getStats: () => request<Stats>("/stats"),
  submitTasks: (tasks: object[]) =>
    request<Task[]>("/tasks", {
      method: "POST",
      body: JSON.stringify({ tasks }),
    }),
};
