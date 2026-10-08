import { Stats } from "@/lib/types";

interface Props {
  stats: Stats;
}

const STAT_ITEMS = [
  { key: "running" as const, label: "Running", color: "text-blue-600" },
  { key: "waiting" as const, label: "Waiting", color: "text-yellow-600" },
  { key: "succeeded" as const, label: "Succeeded", color: "text-green-600" },
  { key: "failed" as const, label: "Failed", color: "text-red-600" },
  { key: "blocked" as const, label: "Blocked", color: "text-gray-500" },
  { key: "cancelled" as const, label: "Cancelled", color: "text-purple-600" },
];

export function StatsBar({ stats }: Props) {
  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-4 bg-white border rounded-lg p-4 shadow-sm">
      {STAT_ITEMS.map(({ key, label, color }) => (
        <div key={key} className="text-center">
          <div className={`text-2xl font-bold ${color}`}>{stats[key]}</div>
          <div className="text-xs text-gray-500 mt-0.5">{label}</div>
        </div>
      ))}
    </div>
  );
}
