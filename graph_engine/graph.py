import networkx as nx
import random
import math
import os
import pickle

graph = nx.DiGraph()

def haversine(coord1, coord2):
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371  # Radius of Earth in kilometers

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c  # Distance in kilometers


city_coords = {
    # North America
    "New York":              (40.7128,   -74.0060),   
    "Los Angeles":           (34.0522,  -118.2437),   
    "Toronto":               (43.6511,   -79.3470),   
    "Chicago":               (41.8781,   -87.6298),   
    "San Francisco":         (37.7749,  -122.4194),   
    "Vancouver":             (49.2827,  -123.1207),   
    "Mexico City":           (19.4326,   -99.1332),   
    "Miami":                 (25.7617,   -80.1918),   
    "Montreal":              (45.5017,   -73.5673),   
    "Houston":               (29.7604,   -95.3698),   
    "Seattle":               (47.6062,  -122.3321),   
    "Boston":                (42.3601,   -71.0589),   
    "Atlanta":               (33.7490,   -84.3880),   
    "Philadelphia":          (39.9526,   -75.1652),   
    "Dallas":                (32.7767,   -96.7970),
    "Phoenix":               (33.4484,  -112.0740),

    # South America
    "Sao Paulo":             (-23.5505,  -46.6333),   
    "Buenos Aires":          (-34.6037,  -58.3816),   
    "Lima":                  (-12.0464,  -77.0428),   
    "Bogota":                (4.7110,   -74.0721),    
    "Santiago":              (-33.4489,  -70.6693),   
    "Caracas":               (10.4806,   -66.9036),   
    "Quito":                 (-0.1807,  -78.4678),    
    "La Paz":                (-16.4897,  -68.1193),   
    "Montevideo":            (-34.9011,  -56.1645),   
    "Asuncion":              (-25.2637,  -57.5759),   
    "Medellin":              (6.2442,   -75.5812),    
    "Cali":                  (3.4516,   -76.5319),    
    "Salvador":              (-12.9777,  -38.5016),   
    "Brasilia":              (-15.8267,  -47.9218),   
    "Rio de Janeiro":        (-22.9068,  -43.1729),   

    # Europe
    "London":                (51.5074,   -0.1278),    
    "Paris":                 (48.8566,    2.3522),    
    "Berlin":                (52.5200,   13.4050),    
    "Madrid":                (40.4168,   -3.7038),    
    "Rome":                  (41.9028,   12.4964),    
    "Vienna":                (48.2085,   16.3721),    
    "Amsterdam":             (52.3702,    4.8952),    
    "Brussels":              (50.8503,    4.3517),    
    "Copenhagen":            (55.6761,   12.5683),    
    "Warsaw":                (52.2297,   21.0122),    
    "Prague":                (50.0755,   14.4378),    
    "Zurich":                (47.3769,    8.5417),    
    "Athens":                (37.9838,   23.7275),    
    "Oslo":                  (59.9139,   10.7522),    
    "Stockholm":             (59.3293,   18.0686),    
    "Lisbon":                (38.7169,   -9.1399),    
    "Dublin":                (53.3498,   -6.2603),    
    "Budapest":              (47.4979,   19.0402),    

    # Africa
    "Cairo":                 (30.0444,   31.2357),    
    "Johannesburg":          (-26.2041,   28.0473),   
    "Lagos":                 (6.5244,     3.3792),    
    "Nairobi":               (-1.2921,    36.8219),   
    "Casablanca":            (33.5731,   -7.5898),    
    "Addis Ababa":           (9.0054,    38.7636),    
    "Accra":                 (5.6037,     -0.1870),   
    "Dakar":                 (14.6928,   -17.4467),   
    "Abidjan":               (5.3453,     -4.0244),   
    "Kampala":               (0.3476,     32.5825),   
    "Kinshasa":              (-4.4419,    15.2663),   
    "Tunis":                 (36.8065,    10.1815),   
    "Algiers":               (36.7538,     3.0588),   
    "Luanda":                (-8.8390,    13.2894),   
    "Khartoum":              (15.5007,    32.5599),   
    "Harare":                (-17.8252,   31.0335),   
    "Gaborone":              (-24.6282,   25.9231),   

    # Asia
    "Tokyo":                 (35.6895,   139.6917),   
    "Mumbai":                (19.0760,    72.8777),   
    "Beijing":               (39.9042,   116.4074),   
    "Shanghai":              (31.2304,   121.4737),   
    "Bangkok":               (13.7563,   100.5018),   
    "Seoul":                 (37.5665,   126.9780),   
    "Jakarta":               (-6.1751,   106.8650),   
    "Manila":                (14.5995,   120.9842),   
    "Singapore":             (1.3521,    103.8198),   
    "Kuala Lumpur":          (3.1390,    101.6869),   
    "Delhi":                 (28.6139,    77.2090),   
    "Hanoi":                 (21.0278,   105.8342),   
    "Taipei":                (25.0328,   121.5654),   
    "Dubai":                 (25.2048,    55.2708),   
    "Riyadh":                (24.7136,    46.6753),   
    "Dhaka":                 (23.8103,    90.4125),   

    # Oceania
    "Sydney":                (-33.8688,  151.2093),   
    "Melbourne":             (-37.8136,  144.9631),   
    "Brisbane":              (-27.4698,  153.0251),   
    "Perth":                 (-31.9505,  115.8605),   
    "Auckland":              (-36.8485,  174.7633),   
    "Wellington":            (-41.2865,  174.7762),   
    "Christchurch":          (-43.5321,  172.6362),   
    "Canberra":              (-35.2809,  149.1300),   
    "Adelaide":              (-34.9285,  138.6007),   
    "Hobart":                (-42.8821,  147.3272),   
    "Suva":                  (-18.1248,  178.4501),   
    "Noumea":                (-22.2760,  166.4572),   
    "Port Moresby":          (-9.4438,   147.1803),   
    "Nuku'alofa":            (-21.1310, -175.2041),   
    "Apia":                  (-13.8500, -171.7600),   
    "Gold Coast":            (-28.0167,  153.4000),   
    "Darwin":                (-12.4634,  130.8456),   
    "Hamilton":              (-37.7870,  175.2793),   
}

continents = {
    "North America": ["New York", "Los Angeles", "Toronto", "Chicago", "Houston", "Vancouver", "San Francisco", "Mexico City", "Miami", "Atlanta", "Montreal", "Seattle", "Boston", "Phoenix", "Dallas"],
    "South America": ["Sao Paulo", "Buenos Aires", "Lima", "Bogota", "Santiago", "Caracas", "Quito", "La Paz", "Montevideo", "Asuncion", "Cali", "Medellin", "Rio de Janeiro", "Brasilia", "Salvador"],
    "Europe": ["London", "Paris", "Berlin", "Madrid", "Rome", "Amsterdam", "Vienna", "Zurich", "Oslo", "Warsaw", "Lisbon", "Dublin", "Prague", "Budapest", "Copenhagen"],
    "Africa": ["Lagos", "Cairo", "Nairobi", "Accra", "Johannesburg", "Algiers", "Casablanca", "Addis Ababa", "Dakar", "Tunis", "Kampala", "Luanda", "Abidjan", "Harare", "Gaborone"],
    "Asia": ["Tokyo", "Beijing", "Shanghai", "Delhi", "Mumbai", "Seoul", "Bangkok", "Singapore", "Kuala Lumpur", "Jakarta", "Hanoi", "Manila", "Taipei", "Dhaka", "Riyadh"],
    "Oceania": ["Sydney", "Melbourne", "Auckland", "Brisbane", "Perth", "Wellington", "Adelaide", "Canberra", "Hobart", "Gold Coast", "Darwin", "Hamilton", "Christchurch", "Suva", "Noumea"]
}

def haversine(coord1, coord2):
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371 

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c  

# Add nodes with coordinates and region
for region, cities in continents.items():
    for city in cities:
        if city in city_coords:
            graph.add_node(city, region=region, coords=city_coords[city])


# Add intra-continental edges with all metrics
for region, cities in continents.items():
    for city in cities:
        if city not in city_coords:
            continue
        connections = [c for c in cities if c != city and c in city_coords]
        selected = random.sample(connections, k=min(2, len(connections)))
        for target in selected:
            dist = haversine(city_coords[city], city_coords[target])
            cost = round(dist * random.uniform(0.3, 0.7), 2)
            time = round((dist / 100) * random.uniform(0.8, 1.2), 2)
            risk = round(random.uniform(0.01, 0.08), 2)
            graph.add_edge(city, target,
                           distance=round(dist, 2),
                           cost=cost,
                           time=time,
                           risk=risk)

# Add inter-continental links (bidirectional) with metrics
inter_links = [
    ("New York", "London"), ("Tokyo", "San Francisco"), ("Paris", "Cairo"),
    ("Johannesburg", "Mumbai"), ("Sydney", "Los Angeles"),
    ('Mexico City', 'Brasília'), ('Rome', 'Delhi'), ('Perth', 'Jakarta')
]

for u, v in inter_links:
    if u in city_coords and v in city_coords:
        dist = haversine(city_coords[u], city_coords[v])
        cost = round(dist * random.uniform(0.3, 0.7), 2)
        time = round((dist / 100) * random.uniform(0.8, 1.08), 2)
        risk = round(random.uniform(0.01, 0.2), 2)
        for src, tgt in [(u, v), (v, u)]:
            graph.add_edge(src, tgt,
                           distance=round(dist, 2),
                           cost=cost,
                           time=time,
                           risk=risk)

# Save to disk
output_dir = "graph_data"
os.makedirs(output_dir, exist_ok=True)
with open(os.path.join(output_dir, "world_graph.gpickle"), "wb") as f:
    pickle.dump(graph, f)

print("[✓] Graph saved to graph_data/world_graph.gpickle with real-world distances, costs, time, and risk")