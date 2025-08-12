# 📦 Distributed Package Delivery Tracker

A distributed, simulation-driven package delivery tracking system inspired by real-world logistics platforms.  
It simulates worldwide package movement using graph-based routing, tracks status updates in real time, and integrates distributed database concepts.

<img width="3840" height="1850" alt="image" src="https://github.com/user-attachments/assets/7b49c55e-c327-4d07-bffc-4505343ac25d" />

---

## 🚀 Features

- **FastAPI Backend** — REST API for package creation, status tracking, and querying.
- **MongoDB Integration** — Stores packages, histories, and updates with structured schemas.
- **Graph-based Routing Engine** —  
  - Nodes: Major cities across all continents.  
  - Edges: Weighted by cost or time.  
  - Uses shortest path algorithms to compute delivery routes.
- **Real-time Simulation** — Moves packages hop-by-hop according to:  
  - `1 second IRL = 2 hours simulated time`.
- **RabbitMQ Messaging** — Decoupled services for package creation and simulation via a queue.
- **Distributed System Design** — Future support for multi-region distributed MongoDB.
- **Environment Variables** — `.env` for configuration of database, messaging, and paths.
- **Phase 3 Plan** — Integrating full distributed database simulation.

---

## 🛠 Technologies Used

- **Backend**: Python, FastAPI
- **Database**: MongoDB
- **Graph Processing**: NetworkX
- **Messaging**: RabbitMQ
- **Containerization**: Docker
- **Config Management**: python-dotenv
- **Scheduling & Simulation**: asyncio

---

## 🧮 How It Works

1. **Package Creation** — User creates a package via the API → stored in MongoDB → published to RabbitMQ.  
2. **Simulation** — The `Simulation` service consumes messages, finds shortest route in the graph, and simulates package movement in real time.  
3. **Database Updates** — At every hop, the current location and timestamp are updated in MongoDB.  
4. **Query** — User can check the package status via API at any time.  

---

## 🌍 Current Graph Details

- **Regions**: Continents as major clusters.  
- **Cities per Continent**: ~15.  
- **Edges**: Represent transportation routes.  
- **Weight Types**: Time or cost (configurable per package).  

---

## 📅 Development Phases

- **Phase 1 ✅** — FastAPI + MongoDB integration with CRUD for packages.  
- **Phase 2 ✅** — Graph engine, real-time simulation, RabbitMQ messaging system.  
- **Phase 3 🚧** — Distributed MongoDB simulation with multi-region replication.  

---

## 📜 License

MIT License — free to use and modify.

