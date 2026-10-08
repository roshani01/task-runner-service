// Types matching backend schemas
export type TaskStatus =
  | "WAITING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "BLOCKED"
  | "CANCELLED";

export interface TaskAttempt {
  id: number;
  attempt_number: number;
  started_at: string;
  completed_at: string | null;
  outcome: string | null;
  error_message: string | null;
}

export interface Task {
  id: string;
  name: string;
  status: TaskStatus;
  duration: number;
  failure_rate: number;
  max_retries: number;
  attempts: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  dependency_ids: string[];
  history: TaskAttempt[];
}

export interface Stats {
  running: number;
  waiting: number;
  succeeded: number;
  failed: number;
  blocked: number;
  cancelled: number;
  total: number;
}

export interface TaskSubmitItem {
  id: string;
  name: string;
  duration?: number;
  failure_rate?: number;
  max_retries?: number;
  depends_on?: string[];
}
