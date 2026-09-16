"""
FastAPI Backend - Main application entry point.
Exposes REST + WebSocket endpoints for the Digital Twin dashboard.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulation.simulation_engine import get_engine, FaultInjectionRequest
from ai.vpms import get_vpms
from ai.autoencoder import AnomalyDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Global State ───────────────────────────────────────────────────────────────
engine = None
vpms = None
anomaly_detector = None
_ws_clients: list[WebSocket] = []


async def broadcast_state(state: dict):
    """Push grid state to all connected WebSocket clients."""
    disconnected = []
    for ws in _ws_clients:
        try:
            await ws.send_json(state)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _ws_clients.remove(ws)


def on_simulation_step(state: dict):
    """Called on every simulation tick — triggers broadcast to WS clients."""
    if anomaly_detector:
        ai_result = anomaly_detector.update(state)
        state["ai_anomaly"] = ai_result
    else:
        state["ai_anomaly"] = {"score": 0.0, "anomaly": False, "confidence": 0.0}

    asyncio.run_coroutine_threadsafe(broadcast_state(state), _event_loop)


_event_loop = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize and start all services."""
    global engine, vpms, anomaly_detector, _event_loop
    _event_loop = asyncio.get_running_loop()

    logger.info("🚀 Starting Digital Twin services...")

    engine = get_engine()
    engine.add_listener(on_simulation_step)
    engine.run_in_background(realtime=True)
    logger.info("✅ Simulation Engine started.")

    vpms = get_vpms()
    vpms.attach_engine(engine)
    vpms.start()
    logger.info("✅ vPMS Controller started.")

    # Load pre-trained model if available
    anomaly_detector = AnomalyDetector(threshold=0.025)
    model_path = os.path.join(os.path.dirname(__file__), "models", "autoencoder_final.pt")
    if os.path.exists(model_path):
        anomaly_detector.load(model_path)
        logger.info(f"✅ Anomaly Detector loaded from {model_path}")
    else:
        logger.warning("⚠️  No pre-trained model found. Running in untrained mode (random scores).")

    yield

    # Shutdown
    engine.stop()
    vpms.stop()
    logger.info("Services stopped.")


# ── App Factory ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Ship Digital Twin API",
    description="Software-Defined Virtual Digital Twin for Shipboard Power Management",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ──────────────────────────────────────────────────

class FaultRequest(BaseModel):
    component_id: str
    fault_type: str       # overload | short_circuit | governor_loss | avr_failure | load_trip | load_shed
    magnitude: float = 1.0
    duration_s: float = 30.0

class GeneratorCommand(BaseModel):
    action: str           # "start" or "stop"
    gen_id: str


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"status": "online", "service": "Ship Digital Twin API"}


@app.get("/api/state", tags=["Simulation"])
def get_current_state():
    """Get the complete current grid state snapshot."""
    if not engine:
        raise HTTPException(503, "Simulation not running")
    state = engine.get_state()
    if anomaly_detector:
        state["ai_anomaly"] = anomaly_detector.get_last_result()
    return state


@app.post("/api/fault/inject", tags=["Fault Injection"])
def inject_fault(req: FaultRequest):
    """
    Inject a fault into the simulation.

    Supported fault types per component:
    - Generators: overload, short_circuit, governor_loss, avr_failure
    - Loads: load_trip, load_shed
    """
    if not engine:
        raise HTTPException(503, "Simulation not running")
    fault = FaultInjectionRequest(
        component_id=req.component_id,
        fault_type=req.fault_type,
        magnitude=req.magnitude,
        duration_s=req.duration_s,
    )
    engine.inject_fault(fault)
    return {"status": "fault_injected", "component": req.component_id, "type": req.fault_type}


@app.delete("/api/fault/{component_id}", tags=["Fault Injection"])
def clear_fault(component_id: str):
    """Manually clear an active fault on a component."""
    if not engine:
        raise HTTPException(503, "Simulation not running")
    engine.clear_fault(component_id)
    return {"status": "fault_cleared", "component": component_id}


@app.get("/api/faults/active", tags=["Fault Injection"])
def get_active_faults():
    """List all currently active faults."""
    if not engine:
        raise HTTPException(503, "Simulation not running")
    state = engine.get_state()
    return {"active_faults": state.get("active_faults", {})}


@app.post("/api/generator/command", tags=["Generator Control"])
def control_generator(cmd: GeneratorCommand):
    """Start or stop a generator."""
    if not engine:
        raise HTTPException(503, "Simulation not running")
    if cmd.action == "start":
        engine.start_generator(cmd.gen_id)
    elif cmd.action == "stop":
        engine.stop_generator(cmd.gen_id)
    else:
        raise HTTPException(400, "action must be 'start' or 'stop'")
    return {"status": "ok", "generator": cmd.gen_id, "action": cmd.action}


@app.get("/api/vpms/status", tags=["vPMS"])
def get_vpms_status():
    """Get the current vPMS controller status."""
    if not vpms:
        raise HTTPException(503, "vPMS not running")
    return vpms.get_status()


@app.get("/api/ai/anomaly", tags=["AI"])
def get_anomaly_status():
    """Get the latest AI anomaly detection result."""
    if not anomaly_detector:
        raise HTTPException(503, "Anomaly detector not initialized")
    return anomaly_detector.get_last_result()


# ── Predefined Fault Scenarios ─────────────────────────────────────────────────

SCENARIOS = {
    "blackout_test": [
        FaultRequest(component_id="GEN_01", fault_type="short_circuit", magnitude=1.0, duration_s=15.0),
        FaultRequest(component_id="GEN_02", fault_type="short_circuit", magnitude=1.0, duration_s=15.0),
    ],
    "overload_cascade": [
        FaultRequest(component_id="GEN_01", fault_type="overload", magnitude=0.8, duration_s=60.0),
    ],
    "voltage_dip": [
        FaultRequest(component_id="GEN_01", fault_type="avr_failure", magnitude=0.7, duration_s=45.0),
    ],
    "governor_fault": [
        FaultRequest(component_id="GEN_02", fault_type="governor_loss", magnitude=0.9, duration_s=30.0),
    ],
}


@app.post("/api/scenario/{scenario_name}", tags=["Fault Injection"])
def run_scenario(scenario_name: str):
    """Run a predefined fault scenario."""
    if scenario_name not in SCENARIOS:
        raise HTTPException(404, f"Scenario '{scenario_name}' not found. Available: {list(SCENARIOS.keys())}")
    if not engine:
        raise HTTPException(503, "Simulation not running")
    for req in SCENARIOS[scenario_name]:
        fault = FaultInjectionRequest(
            component_id=req.component_id,
            fault_type=req.fault_type,
            magnitude=req.magnitude,
            duration_s=req.duration_s,
        )
        engine.inject_fault(fault)
    return {"status": "scenario_started", "scenario": scenario_name}


@app.get("/api/scenarios", tags=["Fault Injection"])
def list_scenarios():
    return {"scenarios": list(SCENARIOS.keys())}


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws/grid")
async def websocket_grid(websocket: WebSocket):
    """
    Real-time WebSocket stream of grid state updates.
    Clients receive a JSON update every simulation tick (~0.5s).
    """
    await websocket.accept()
    _ws_clients.append(websocket)
    logger.info(f"WebSocket client connected. Total: {len(_ws_clients)}")
    try:
        while True:
            # Keep alive: accept any client message (ping/pong)
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(_ws_clients)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
