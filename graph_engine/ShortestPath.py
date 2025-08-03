import networkx as nx
import pickle


def shortest_path_between_cities(graph: nx.DiGraph, source: str, target: str, weight: str):
    if source not in graph:
        return f"Source city '{source}' not found in graph."
    if target not in graph:
        return f"Target city '{target}' not found in graph."

    try:
        path = nx.dijkstra_path(graph, source, target, weight=weight)

        # Initialize totals
        total_distance = 0.0
        total_cost = 0.0
        total_time = 0.0
        survival = 1.0  # used to compute risk as 1 - survival

        for i in range(len(path) - 1):
            edge = graph[path[i]][path[i + 1]]
            total_distance += edge.get("distance", 0)
            total_cost += edge.get("cost", 0)
            total_time += edge.get("time", 0)
            risk = edge.get("risk", 0)
            survival *= (1 - risk)  # multiply survival

        accumulated_risk = 1 - survival

        return {
            "path": path,
            "used_metric": weight,
            "totals": {
                "distance_km": round(total_distance, 2),
                "cost_usd": round(total_cost, 2),
                "time_hr": round(total_time, 2),
                "risk_score": round(accumulated_risk, 4)
            }
        }

    except nx.NetworkXNoPath:
        return f"No path found between {source} and {target}."


with open("graph_data/world_graph.gpickle", "rb") as f:
    graph = pickle.load(f)

result = shortest_path_between_cities(graph, "New York", "Tokyo", weight="distance")

if isinstance(result, dict):
    print("📦 Shortest path from", result["path"][0], "to", result["path"][-1], f"(optimized by {result['used_metric']})")
    print(" → ".join(result["path"]))
    print("\nTotal metrics along this path:")
    for metric, value in result["totals"].items():
        print(f"  {metric.replace('_', ' ').capitalize()}: {value}")
else:
    print(result)  # prints error message if path not found
