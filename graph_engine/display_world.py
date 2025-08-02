import plotly.graph_objects as go
import networkx as nx
import pickle
import os

# Load graph
with open("graph_data/world_graph.gpickle", "rb") as f:
    graph = pickle.load(f)

# Create lists for nodes and edges
node_lats = []
node_lons = []
node_names = []

edge_lats = []
edge_lons = []

for node, data in graph.nodes(data=True):
    lat, lon = data["coords"]
    node_lats.append(lat)
    node_lons.append(lon)
    node_names.append(node)

for u, v in graph.edges():
    if "coords" not in graph.nodes[u] or "coords" not in graph.nodes[v]:
        continue
    lat1, lon1 = graph.nodes[u]["coords"]
    lat2, lon2 = graph.nodes[v]["coords"]
    edge_lats += [lat1, lat2, None]
    edge_lons += [lon1, lon2, None]

# Plot with plotly on a map
fig = go.Figure()

# Add edges
fig.add_trace(go.Scattergeo(
    lon=edge_lons,
    lat=edge_lats,
    mode='lines',
    line=dict(width=0.8, color='blue'),
    opacity=0.4,
    showlegend=False
))

# Add nodes
fig.add_trace(go.Scattergeo(
    lon=node_lons,
    lat=node_lats,
    mode='markers+text',
    text=node_names,
    textposition='top center',
    marker=dict(
        size=6,
        color='red',
        line=dict(width=0.5, color='black')
    ),
    name='Cities'
))

fig.update_layout(
    title='📦 Global Package Network',
    geo=dict(
        showland=True,
        landcolor='rgb(243, 243, 243)',
        countrycolor='gray',
        showcoastlines=True,
        coastlinecolor='gray',
        projection_type='natural earth',
    ),
    margin={"r":0,"t":30,"l":0,"b":0}
)

fig.show()
