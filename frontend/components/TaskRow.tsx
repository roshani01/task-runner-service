"use client";

import { useState } from "react";
import { Task } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";
import { api } from "@/lib/api";

interface Props {
  task: Task;
  allTasks: Task[];
  onUpdate: () => void;
}

export function TaskRow({ task, allTasks, onUpdate }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const depNames = task.dependency_ids
    .map((id) => allTasks.find((t) => t.id === id)?.name ?? id.slice(0, 8))
    .join(", ");

  const handleCancel = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setCancelling(true);
    try {
      await api.cancelTask(task.id);
      onUpdate();
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setCancelling(false);
    }
  };

  return (
    <>
      <tr
        className="border-b hover:bg-gray-50 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-3 py-2 font-medium text-sm text-gray-800">{task.name}</td>
        <td className="px-3 py-2">
          <StatusBadge status={task.status} />
        </td>
        <td className="px-3 py-2 text-sm text-gray-600 text-center">{task.attempts}</td>
        <td className="px-3 py-2 text-sm text-gray-500">{depNames || "—"}</td>
        <td className="px-3 py-2 text-sm text-gray-500">{task.duration}s</td>
        <td className="px-3 py-2">
          {task.status === "WAITING" && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="text-xs text-red-600 hover:text-red-800 disabled:opacity-40"
            >
              Cancel
            </button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-gray-50">
          <td colSpan={6} className="px-4 py-2">
            <div className="text-xs text-gray-600 space-y-1">
              <div>
                <span className="font-medium">ID:</span> {task.id}
              </div>
              {task.error_message && (
                <div className="text-red-600">
                  <span className="font-medium">Error:</span> {task.error_message}
                </div>
              )}
              {task.history.length > 0 && (
                <div>
                  <div className="font-medium mb-1">Attempt history:</div>
                  <table className="text-xs w-full">
                    <thead>
                      <tr className="text-gray-500">
                        <th className="text-left pr-4">#</th>
                        <th className="text-left pr-4">Outcome</th>
                        <th className="text-left pr-4">Started</th>
                        <th className="text-left">Completed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {task.history.map((a) => (
                        <tr key={a.id}>
                          <td className="pr-4">{a.attempt_number}</td>
                          <td className={`pr-4 ${a.outcome === "failed" ? "text-red-600" : "text-green-600"}`}>
                            {a.outcome ?? "—"}
                          </td>
                          <td className="pr-4">{new Date(a.started_at).toLocaleTimeString()}</td>
                          <td>
                            {a.completed_at
                              ? new Date(a.completed_at).toLocaleTimeString()
                              : "running…"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
