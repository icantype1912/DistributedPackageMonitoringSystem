import plotly.graph_objects as go
import networkx as nx
import pickle
import math

# Load graph
with open("/home/adi/dev/distpack/graph_engine/graph_data/world_graph.gpickle", "rb") as f:
    graph = pickle.load(f)

# Node data
node_lats = []
node_lons = []
node_names = []
node_hover = []

for node, data in graph.nodes(data=True):
    if "coords" not in data:
        continue
    lat, lon = data["coords"]
    node_lats.append(lat)
    node_lons.append(lon)
    node_names.append(node)
    node_hover.append(f"{node}<br>Region: {data.get('region', 'N/A')}<br>Lat: {lat:.2f}, Lon: {lon:.2f}")

# Edge data
edge_traces = []

for u, v, attrs in graph.edges(data=True):
    if "coords" not in graph.nodes[u] or "coords" not in graph.nodes[v]:
        continue
    lat1, lon1 = graph.nodes[u]["coords"]
    lat2, lon2 = graph.nodes[v]["coords"]

    risk = attrs.get("risk", 0.1)

    # Normalize risk to 0–1 within 0.01 to 0.2 range
    risk_norm = min(max((risk - 0.01) / (0.08 - 0.01), 0), 1)
    risk_norm = math.pow(risk_norm, 2.5)

    edge_traces.append(go.Scattergeo(
        lon=[lon1, lon2],
        lat=[lat1, lat2],
        mode='lines',
        line=dict(
            width=1,
            color=f"rgba({int(255 * risk_norm)}, {int(255 * (1 - risk_norm))}, 50, 0.3)"
        ),
        hoverinfo='skip',
        showlegend=False
    ))

# Plot
fig = go.Figure()

# Add all edge traces
for trace in edge_traces:
    fig.add_trace(trace)

# Add nodes
fig.add_trace(go.Scattergeo(
    lon=node_lons,
    lat=node_lats,
    mode='markers+text',
    text=node_names,
    hovertext=node_hover,
    hoverinfo='text',
    textposition='top center',
    marker=dict(
        size=6,
        color='crimson',
        line=dict(width=0.5, color='black')
    ),
    name='Cities'
))

fig.update_layout(
    title='📦 Global Package Network (Cities only hover)',
    geo=dict(
        showland=True,
        landcolor='rgb(243, 243, 243)',
        countrycolor='gray',
        showcoastlines=True,
        coastlinecolor='gray',
        projection_type='natural earth',
    ),
    margin={"r": 0, "t": 30, "l": 0, "b": 0}
)

fig.show()
