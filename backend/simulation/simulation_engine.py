"""
Main Simulation Engine.
Orchestrates the entire virtual shipboard power grid simulation loop.
Integrates generators, bus bar, loads, vPMS, and fault injection.
"""

import time
import threading
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.generator import DieselGenerator, GeneratorParams
from simulation.load import ShipLoad, create_default_loads
from simulation.bus_bar import BusBar

logger = logging.getLogger(__name__)


@dataclass
class FaultInjectionRequest:
    component_id: str
    fault_type: str      # 'overload', 'short_circuit', 'governor_loss', 'avr_failure', 'load_trip', 'load_shed'
    magnitude: float = 1.0
    duration_s: float = 30.0


class SimulationEngine:
    """
    The heart of the Digital Twin: a real-time virtual shipboard grid.
    Runs in its own background thread at a configurable time-step.
    """

    DT = 0.5   # Simulation time step in seconds (wall-clock: 0.5s per step by default)

    def __init__(self):
        self._running = False
        self._lock = threading.Lock()
        self._sim_time = 0.0  # Simulated time in seconds
        self._listeners: List[Callable] = []

        # ── Instantiate Components ─────────────────────────────────────────────
        self.generators: List[DieselGenerator] = [
            DieselGenerator("GEN_01", GeneratorParams(rated_kw=1500.0)),
            DieselGenerator("GEN_02", GeneratorParams(rated_kw=1500.0)),
            DieselGenerator("GEN_03", GeneratorParams(rated_kw=1000.0)),
        ]
        self.loads: List[ShipLoad] = create_default_loads()
        self.bus_bar = BusBar("MAIN_BUS")

        # Active faults: { component_id: (fault_type, magnitude, remaining_s) }
        self._active_faults: Dict[str, tuple] = {}

        # Start GEN_01 and GEN_02 online by default
        self.generators[0].start()
        self.generators[1].start()

        # Initialize loads
        for load in self.loads:
            load.step(dt=self.DT, V_bus=440.0)

        # ── Pre-warm simulation to steady state ────────────────────────────────
        # Run 200 fast steps (= 100s simulated) so generators reach operating
        # temperature (~80-90°C) before the real-time loop and AI begin.
        # This prevents false AI alarms during the cold-start transient.
        logger.info("Pre-warming simulation to steady state (200 steps)...")
        for _ in range(200):
            self.bus_bar.solve_power_flow(self.generators, self.loads, dt=self.DT)

        logger.info("SimulationEngine initialized: GEN_01 + GEN_02 online, 6 loads active.")

    def add_listener(self, callback: Callable):
        """Register a callback that receives the grid state dict on each step."""
        self._listeners.append(callback)

    def inject_fault(self, req: FaultInjectionRequest):
        """Thread-safe fault injection."""
        with self._lock:
            self._active_faults[req.component_id] = (req.fault_type, req.magnitude, req.duration_s)
            logger.warning(f"⚡ Fault injected: {req.fault_type} on {req.component_id} (duration: {req.duration_s}s)")

    def clear_fault(self, component_id: str):
        """Manually clear a fault on a component."""
        with self._lock:
            self._active_faults.pop(component_id, None)
            for gen in self.generators:
                if gen.gen_id == component_id:
                    gen.clear_fault()
            logger.info(f"✅ Fault cleared on {component_id}")

    def start_generator(self, gen_id: str):
        with self._lock:
            for gen in self.generators:
                if gen.gen_id == gen_id:
                    gen.start()
                    logger.info(f"GEN {gen_id} brought ONLINE.")
                    return
        raise ValueError(f"Generator {gen_id} not found.")

    def stop_generator(self, gen_id: str):
        with self._lock:
            for gen in self.generators:
                if gen.gen_id == gen_id:
                    gen.stop()
                    logger.info(f"GEN {gen_id} taken OFFLINE.")
                    return
        raise ValueError(f"Generator {gen_id} not found.")

    def _apply_active_faults(self):
        """Apply all active faults and tick their timers."""
        expired = []
        for comp_id, (fault_type, magnitude, remaining) in list(self._active_faults.items()):
            # Apply to generator
            for gen in self.generators:
                if gen.gen_id == comp_id:
                    gen.apply_fault(fault_type, magnitude)

            # Apply load trips
            for load in self.loads:
                if load.profile.load_id == comp_id:
                    if fault_type == "load_trip":
                        load.trip()
                    elif fault_type == "load_shed":
                        load.shed()

            # Decrement timer
            new_remaining = remaining - self.DT
            if new_remaining <= 0:
                expired.append(comp_id)
            else:
                self._active_faults[comp_id] = (fault_type, magnitude, new_remaining)

        # Clear expired faults
        for comp_id in expired:
            self._active_faults.pop(comp_id, None)
            for gen in self.generators:
                if gen.gen_id == comp_id:
                    gen.clear_fault()
            logger.info(f"Fault auto-cleared on {comp_id}")

    def _step(self):
        """Execute one simulation time step."""
        with self._lock:
            self._apply_active_faults()
            self.bus_bar.solve_power_flow(self.generators, self.loads, self.DT)
            self._sim_time += self.DT

    def get_state(self) -> dict:
        """Return a complete snapshot of the current grid state."""
        with self._lock:
            return {
                "sim_time_s": round(self._sim_time, 2),
                "bus_bar": self.bus_bar.get_state(),
                "generators": [g.get_state() for g in self.generators],
                "loads": [l.get_state() for l in self.loads],
                "active_faults": {
                    k: {"fault_type": v[0], "magnitude": v[1], "remaining_s": round(v[2], 1)}
                    for k, v in self._active_faults.items()
                },
            }

    def run(self, realtime: bool = True):
        """
        Start the simulation loop.
        realtime=True: wall clock paced (DT seconds between steps).
        realtime=False: as fast as possible (for data generation / training).
        """
        self._running = True
        logger.info(f"🚀 SimulationEngine running (realtime={realtime}, dt={self.DT}s)")
        while self._running:
            t0 = time.time()
            self._step()
            state = self.get_state()
            for cb in self._listeners:
                try:
                    cb(state)
                except Exception as e:
                    logger.error(f"Listener error: {e}")

            if realtime:
                elapsed = time.time() - t0
                sleep_t = max(0, self.DT - elapsed)
                time.sleep(sleep_t)

    def stop(self):
        self._running = False
        logger.info("SimulationEngine stopped.")

    def run_in_background(self, realtime: bool = True) -> threading.Thread:
        """Convenience: start simulation in a daemon thread."""
        t = threading.Thread(target=self.run, args=(realtime,), daemon=True)
        t.start()
        return t


# ── Singleton instance shared across the application ──────────────────────────
_engine: Optional[SimulationEngine] = None


def get_engine() -> SimulationEngine:
    global _engine
    if _engine is None:
        _engine = SimulationEngine()
    return _engine
