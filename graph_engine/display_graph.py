import networkx as nx
import matplotlib.pyplot as plt
import pickle

# Load the graph
with open("graph_data/world_graph.gpickle", "rb") as f:
    graph = pickle.load(f)

# Set figure size
plt.figure(figsize=(16, 12))

# Choose a layout — spring is usually best for general-purpose graphs
pos = nx.spring_layout(graph, seed=42)  # or nx.kamada_kawai_layout(graph)

# Draw nodes and edges
nx.draw_networkx_nodes(graph, pos, node_size=500, node_color='skyblue')
nx.draw_networkx_edges(graph, pos, width=1.5, edge_color='gray')
nx.draw_networkx_labels(graph, pos, font_size=10, font_family="sans-serif")

# Optional: Draw edge labels (like costs)
edge_labels = nx.get_edge_attributes(graph, 'cost')
nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=8)

# Remove axes
plt.axis("off")
plt.title("Worldwide Package Delivery Graph")
plt.tight_layout()

# Show the plot
plt.show()
