"use client";

import { useState } from "react";
import { api } from "@/lib/api";

interface Props {
  onSubmitted: () => void;
}

const EXAMPLE_PIPELINE = `[
  {"id": "upload", "name": "Upload Document", "duration": 2, "failure_rate": 0.1},
  {"id": "extract", "name": "Extract Text", "duration": 3, "depends_on": ["upload"]},
  {"id": "summary", "name": "Generate Summary", "duration": 2, "depends_on": ["extract"]},
  {"id": "embed", "name": "Create Embeddings", "duration": 4, "depends_on": ["summary"]}
]`;

export function SubmitForm({ onSubmitted }: Props) {
  const [json, setJson] = useState(EXAMPLE_PIPELINE);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    let tasks: unknown;
    try {
      tasks = JSON.parse(json);
    } catch {
      setError("Invalid JSON");
      setLoading(false);
      return;
    }

    try {
      await api.submitTasks(tasks as object[]);
      onSubmitted();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white border rounded-lg p-4 shadow-sm space-y-3">
      <h2 className="font-semibold text-gray-800">Submit Task Batch</h2>
      <p className="text-xs text-gray-500">
        Paste a JSON array of tasks. Each task needs an <code>id</code> and <code>name</code>.
        Optional: <code>duration</code>, <code>failure_rate</code>, <code>max_retries</code>,{" "}
        <code>depends_on</code>.
      </p>
      <textarea
        value={json}
        onChange={(e) => setJson(e.target.value)}
        rows={10}
        className="w-full font-mono text-xs border rounded p-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
        spellCheck={false}
      />
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <button
        type="submit"
        disabled={loading}
        className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-1.5 rounded text-sm font-medium"
      >
        {loading ? "Submitting…" : "Submit"}
      </button>
    </form>
  );
}
