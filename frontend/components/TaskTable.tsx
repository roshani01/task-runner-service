import { Task } from "@/lib/types";
import { TaskRow } from "./TaskRow";

interface Props {
  tasks: Task[];
  onUpdate: () => void;
}

export function TaskTable({ tasks, onUpdate }: Props) {
  if (tasks.length === 0) {
    return (
      <div className="bg-white border rounded-lg p-8 text-center text-gray-400 shadow-sm">
        No tasks yet. Submit a batch above to get started.
      </div>
    );
  }

  return (
    <div className="bg-white border rounded-lg shadow-sm overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b bg-gray-50">
          <tr>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Task</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">Attempts</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Depends on</th>
            <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Duration</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} allTasks={tasks} onUpdate={onUpdate} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
