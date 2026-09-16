# ShipDT — Software-Defined Virtual Digital Twin
### Shipboard Power Management & AI Fault Diagnosis

A fully software-based Digital Twin for a shipboard electrical grid, running 100% locally on your computer. No physical hardware required.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  React Dashboard (localhost:3000)                   │
│  ├── Real-time charts (Recharts + WebSocket)        │
│  ├── Generator control panel                        │
│  ├── Fault injection UI                             │
│  └── AI anomaly gauge                               │
└────────────────────┬────────────────────────────────┘
                     │ WebSocket / REST
┌────────────────────▼────────────────────────────────┐
│  FastAPI Backend (localhost:8000)                   │
│  ├── SimulationEngine (Physics: SciPy/NumPy)        │
│  │   ├── DieselGenerator (AVR + Governor dynamics)  │
│  │   ├── ShipLoad (3 load types)                    │
│  │   └── BusBar (Power flow + droop control)        │
│  ├── VirtualPMS (Constraint-based controller)       │
│  ├── AnomalyDetector (LSTM Autoencoder, PyTorch)    │
│  └── Fault Injection API                            │
└────────────────────┬────────────────────────────────┘
                     │ Kafka Streaming (optional)
┌────────────────────▼────────────────────────────────┐
│  Apache Kafka (Docker) ← Synthetic Data Generator   │
└─────────────────────────────────────────────────────┘
```

---

## Quick Start (Local — No Docker Required)

### Prerequisites
- Python 3.11+
- Node.js 20+

### Step 1: Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
# API running at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### Step 2: Frontend
```bash
cd frontend
npm install
npm run dev
# Dashboard at http://localhost:3000
```

---

## Train the AI Model (Optional but Recommended)
```bash
cd backend
source venv/bin/activate
python -m ai.train_anomaly
# Model saved to backend/models/autoencoder_final.pt
# Restart backend to load the trained model
```

---

## Run with Docker Compose (Full Stack)
```bash
# From project root
docker compose up --build
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/state` | Full grid snapshot |
| POST | `/api/fault/inject` | Inject a fault |
| DELETE | `/api/fault/{id}` | Clear a fault |
| GET | `/api/faults/active` | List active faults |
| POST | `/api/generator/command` | Start/stop generator |
| GET | `/api/vpms/status` | vPMS controller status |
| GET | `/api/ai/anomaly` | AI anomaly score |
| POST | `/api/scenario/{name}` | Run preset scenario |
| WS | `/ws/grid` | Real-time telemetry stream |

### Fault Injection Example
```bash
curl -X POST http://localhost:8000/api/fault/inject \
  -H "Content-Type: application/json" \
  -d '{"component_id":"GEN_01","fault_type":"overload","magnitude":0.8,"duration_s":30}'
```

### Scenarios
- `blackout_test` — Simultaneous short circuits on both generators
- `overload_cascade` — Sustained generator overload
- `voltage_dip` — AVR failure causing voltage collapse
- `governor_fault` — Frequency deviation from governor loss

---

## Project Structure
```
digital-twin/
├── backend/
│   ├── simulation/
│   │   ├── generator.py        # Diesel generator physics model
│   │   ├── load.py             # Shipboard load models
│   │   ├── bus_bar.py          # Power flow / bus bar model
│   │   └── simulation_engine.py # Main simulation orchestrator
│   ├── ai/
│   │   ├── autoencoder.py      # LSTM Autoencoder definition
│   │   ├── train_anomaly.py    # Training script
│   │   └── vpms.py             # Virtual Power Management System
│   ├── data/
│   │   ├── synthetic_generator.py  # Synthetic data generator
│   │   └── kafka_producer.py       # Kafka streaming producer
│   ├── models/                 # Trained model checkpoints
│   └── main.py                 # FastAPI application
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── GeneratorPanel.jsx
│       │   ├── BusBarMetrics.jsx
│       │   ├── GridChart.jsx
│       │   ├── FaultPanel.jsx
│       │   ├── LoadsPanel.jsx
│       │   └── AnomalyPanel.jsx
│       ├── App.jsx
│       ├── useWebSocket.js
│       └── index.css
└── docker-compose.yml
```

---

## Tech Stack
| Layer | Technology |
|-------|-----------|
| Physics Simulation | Python, NumPy, SciPy |
| AI / Anomaly Detection | PyTorch (LSTM Autoencoder) |
| Backend API | FastAPI, Uvicorn |
| Message Streaming | Apache Kafka (Docker) |
| Frontend | React + Vite |
| Charts | Recharts |
| Containerization | Docker, Docker Compose |
