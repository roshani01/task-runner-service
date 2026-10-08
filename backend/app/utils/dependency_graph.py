"""
Cycle detection for task dependency graphs.

Uses iterative DFS with a recursion-stack colour set rather than Python
recursion so we don't hit stack limits on large graphs.
"""


def detect_cycle(adj: dict[str, list[str]]) -> list[str] | None:
    """
    Return the cycle path if one exists in the directed graph, or None.

    adj maps each node to its list of dependencies (edges point "towards" deps).
    We want to detect if following dependencies ever forms a loop.

    Colours: 0 = unvisited, 1 = in current DFS path, 2 = fully explored.
    """
    color: dict[str, int] = {node: 0 for node in adj}
    parent: dict[str, str | None] = {node: None for node in adj}

    for start in adj:
        if color[start] != 0:
            continue

        stack = [(start, iter(adj.get(start, [])))]
        color[start] = 1

        while stack:
            node, children = stack[-1]
            try:
                child = next(children)
                if color.get(child, 0) == 1:
                    # Found a back-edge — reconstruct the cycle
                    cycle = [child, node]
                    cur = node
                    while parent[cur] != child and parent[cur] is not None:
                        cur = parent[cur]  # type: ignore[assignment]
                        cycle.append(cur)
                    cycle.append(child)
                    cycle.reverse()
                    return cycle
                if color.get(child, 0) == 0:
                    color[child] = 1
                    parent[child] = node
                    stack.append((child, iter(adj.get(child, []))))
            except StopIteration:
                color[node] = 2
                stack.pop()

    return None


def build_adjacency(tasks: list[dict]) -> dict[str, list[str]]:
    """
    Build adjacency list from a list of task dicts with 'id' and 'depends_on'.
    Each node points to its dependencies so cycle detection follows dependency edges.
    """
    adj: dict[str, list[str]] = {}
    for task in tasks:
        adj[task["id"]] = list(task.get("depends_on", []))
    return adj
