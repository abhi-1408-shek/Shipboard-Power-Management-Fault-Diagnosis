# Detailed Project Report (DPR)

## Project Title: Software-Defined Virtual Digital Twin for Shipboard Power Management & Fault Diagnosis

---

## 1. Executive Summary
This project implements a fully virtualized, software-based **Digital Twin (DT)** for Shipboard Power Systems (SPS). Instead of deploying physical hardware or requiring expensive maritime PLCs, this project utilizes Software-in-the-Loop (SIL) methodologies to create a high-fidelity digital replica of a vessel’s electrical grid. 

By combining real-time multi-physics simulation engines with deep learning algorithms, this software suite optimizes power management, validates control logic virtually, and simulates complex fault diagnosis. It provides a completely risk-free, highly accurate environment for testing, predictive analytics, and AI-driven fault detection before any real-world deployment.

## 2. Project Objectives
1. **Virtual Hardware Emulation**: Develop a comprehensive software model of shipboard electrical components (Diesel Generators, Main Bus Bar, Shipboard Loads) using Euler integration-based physics equations.
2. **AI-Driven Fault Diagnosis**: Implement a deep learning model (LSTM Autoencoder) to monitor real-time grid telemetry and instantly detect anomalies or impending failures without hardcoded rules.
3. **Virtual Power Management System (vPMS)**: Deploy a software-based supervisory controller that actively monitors grid health and automatically manages generator load sharing, starting/stopping generators based on power demand.
4. **Interactive Dashboard**: Build a modern, real-time web interface for live telemetry visualization, fault injection, and system monitoring.

---

## 3. System Architecture

The architecture is entirely decoupled and software-defined, operating over standard HTTP and WebSocket protocols.

### 3.1. Physics Simulation Engine (Backend)
- **Language**: Python 3.11+
- **Core Engine**: A custom physics engine running in a background thread at 0.5s ticks. It simulates mechanical power ($P_m$), electrical power ($P_e$), rotor speed ($\omega$), and terminal voltage ($V_t$).
- **Generators**: Modeled with internal Swing Equations, AVR (Automatic Voltage Regulator) models, and Governor models.
- **Bus Bar**: Solves the real-time power flow, calculating instantaneous voltage and frequency based on generator outputs and load demands.

### 3.2. AI Anomaly Detection (Backend)
- **Framework**: PyTorch
- **Model**: Long Short-Term Memory (LSTM) Autoencoder.
- **Workflow**: 
  - Extracts a 10-dimensional feature vector from the live simulation (Voltage, Frequency, Load %, Temperatures, Currents, Imbalance).
  - Normalizes data and feeds it into the LSTM over a rolling 30-step window.
  - The model reconstructs the sequence. The Mean Squared Error (MSE) between the input and reconstruction is the **Anomaly Score**.
  - If the score exceeds a rigorously calibrated threshold (derived from normal steady-state physics), it flags an **Anomaly Detected** state.

### 3.3. Virtual Power Management System (vPMS)
- **Role**: The brain of the ship's grid.
- **Logic**: Monitors the bus voltage and frequency. If total load exceeds 85% capacity, it issues a command to start a standby generator. It also includes a warmup delay to prevent premature actions during a cold-start transient.

### 3.4. Frontend Visualization
- **Framework**: React / Vite / Vanilla CSS (Glassmorphism & Neon Cyberpunk styling).
- **Communication**: Receives live data at 2Hz via WebSockets (`/ws/grid`).
- **Features**: Live charting of Bus Voltage, digital readouts of all generator parameters, and interactive fault injection buttons.

---

## 4. Fault Scenarios Simulated

The Digital Twin supports injecting live faults into the physics engine to validate the vPMS and AI model.

1. **Short Circuit**: Massive drop in terminal voltage; current spikes to 3x rated capacity. The AI instantly flags a massive anomaly.
2. **Governor Loss**: Simulates a mechanical fuel regulation failure. Rotor speed drifts, causing grid frequency to deviate from 60Hz. Detected by AI.
3. **AVR Failure**: The Automatic Voltage Regulator fails, causing terminal voltage to dip. Detected by AI.
4. **Overload**: Sudden spike in load demand. Generator temperatures rise and frequency droops slightly. Detected by vPMS which attempts to compensate.
5. **Blackout Test**: Simultaneous short circuits on multiple generators, collapsing the entire grid to validate ultimate failure states.

---

## 5. Technology Stack

- **Backend**: Python 3.11, FastAPI (Web framework), Uvicorn (ASGI server), PyTorch (AI/ML), NumPy (Physics Math).
- **Frontend**: Node.js, npm, React, Vite, Recharts (for live telemetry graphs), Tailwind CSS / Vanilla CSS.

---

## 6. Installation & Setup Guide

This guide allows anyone to clone the repository and run the Digital Twin on their local machine.

### Prerequisites
1. **Python**: Version 3.11 or higher.
2. **Node.js**: Version 18 or higher (with `npm`).
3. **Git**: To clone the repository.

### Step 1: Clone the Repository
Open your terminal or command prompt and run:
```bash
git clone <your-repository-url>
cd digital-twin
```

### Step 2: Setup the Backend (Python Simulation & AI)
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   - **Mac/Linux**: `source venv/bin/activate`
   - **Windows**: `venv\Scripts\activate`
4. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: This will install FastAPI, Uvicorn, NumPy, and PyTorch)*

### Step 3: Setup the Frontend (React Dashboard)
1. Open a **new terminal window** (keep the backend terminal open).
2. Navigate to the frontend directory from the project root:
   ```bash
   cd digital-twin/frontend
   ```
3. Install the Node modules:
   ```bash
   npm install
   ```

---

## 7. Running the Application

To run the full Digital Twin, you need to run both the backend server and the frontend development server simultaneously.

### Start the Backend
In your backend terminal (with the virtual environment activated), run:
```bash
python main.py
```
*You should see logs indicating the Simulation Engine is pre-warming, the vPMS is starting, and the PyTorch Anomaly Detector is loaded. The API runs on `http://localhost:8000`.*

### Start the Frontend
In your frontend terminal, run:
```bash
npm run dev
```
*This will start the Vite development server, usually on `http://localhost:3000` or `http://localhost:5173`.*

### Access the Dashboard
Open your web browser and navigate to the URL provided by the frontend terminal (e.g., `http://localhost:3000`). 

---

## 8. Demonstration / Interview Guide

When demonstrating this project in an interview, follow this script to show its capabilities:

1. **The Healthy Grid**: Show the dashboard on startup. Explain that the physics engine is running in real-time on the backend. Point out the stable Bus Voltage (440V nominal) and Frequency (60Hz).
2. **The AI Baseline**: Point to the "AI Anomaly Detection" panel. Explain that the PyTorch LSTM is evaluating the live grid state 2 times a second. Because the grid is healthy, the score is near `0.0` and the status is `NORMAL`.
3. **Injecting a Fault**: Click the **Short Circuit** button on the dashboard.
4. **Observing the Physics**: Watch the voltage graph instantly dip. Watch the generator current spike.
5. **Observing the AI**: The AI Reconstruction Error will immediately skyrocket past the threshold, and the gauge will flash **ANOMALY DETECTED**. Explain that the model wasn't explicitly programmed to look for a short circuit; it just recognizes that the physics have drastically deviated from the normal manifold it learned during training.
6. **Recovery**: Wait for the fault duration to expire (or clear it). Watch the physics engine recover the grid voltage, and the AI return to `NORMAL`.

---

## 9. Future Enhancements
- **Hardware-in-the-Loop (HIL) Integration**: Connect the software vPMS to physical maritime PLCs via Modbus TCP.
- **Predictive Maintenance**: Upgrade the LSTM to predict Time-To-Failure (TTF) based on gradual temperature degradation.
- **Cloud Deployment**: Containerize with Docker and deploy to AWS/GCP to allow remote fleet monitoring from ashore.
