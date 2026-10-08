"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Stats, Task } from "@/lib/types";
import { StatsBar } from "@/components/StatsBar";
import { SubmitForm } from "@/components/SubmitForm";
import { TaskTable } from "@/components/TaskTable";

const POLL_INTERVAL_MS = 2000;

export default function Home() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [t, s] = await Promise.all([api.listTasks(), api.getStats()]);
      setTasks(t);
      setStats(s);
      setError(null);
      setLastRefresh(new Date());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    intervalRef.current = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [refresh]);

  return (
    <main className="min-h-screen bg-gray-100">
      <header className="bg-white border-b shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-900">Task Runner</h1>
            <p className="text-xs text-gray-500">Document processing pipeline dashboard</p>
          </div>
          <div className="flex items-center gap-3">
            {lastRefresh && (
              <span className="text-xs text-gray-400">
                Last updated: {lastRefresh.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={refresh}
              className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-2 text-sm">
            Cannot reach backend: {error}
          </div>
        )}

        {stats && <StatsBar stats={stats} />}

        <SubmitForm onSubmitted={refresh} />

        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-semibold text-gray-700">
              Tasks{" "}
              <span className="text-gray-400 font-normal text-sm">
                ({tasks.length} total)
              </span>
            </h2>
          </div>
          <TaskTable tasks={tasks} onUpdate={refresh} />
        </div>
      </div>
    </main>
  );
}
