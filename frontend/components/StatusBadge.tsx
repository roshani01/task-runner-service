import { TaskStatus } from "@/lib/types";

const STATUS_STYLES: Record<TaskStatus, string> = {
  WAITING: "bg-yellow-100 text-yellow-800",
  RUNNING: "bg-blue-100 text-blue-800 animate-pulse",
  SUCCEEDED: "bg-green-100 text-green-800",
  FAILED: "bg-red-100 text-red-800",
  BLOCKED: "bg-gray-100 text-gray-600",
  CANCELLED: "bg-purple-100 text-purple-700",
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}
