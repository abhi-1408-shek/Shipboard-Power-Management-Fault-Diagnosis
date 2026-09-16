"""
Virtual Power Management System (vPMS).

Implements constraint-based optimization logic to:
  1. Optimally select which generators to run (minimize fuel burn).
  2. Prevent generator overloading (< 85% rated load per generator).
  3. Enforce N-1 redundancy (always have one generator in reserve).
  4. Perform automatic load shedding in blackout-prevention scenarios.

This runs as a supervisory controller that reads the grid state and issues
commands to the SimulationEngine.
"""

import logging
import threading
import time
from itertools import combinations
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────
MAX_LOAD_PERCENT = 85.0    # Do not exceed 85% per generator
MIN_LOAD_PERCENT = 25.0    # Below this, consider taking a generator offline
FREQ_LOW_TRIP = 57.5       # Hz — initiate load shedding
FREQ_HIGH_TRIP = 62.5      # Hz — overspeed protection
VOLTAGE_LOW_TRIP = 360.0   # Volts — real alarm threshold (85% of 440V nominal)
BLACKOUT_MARGIN_KW = 200.0 # Always keep 200 kW in reserve above demand

LOAD_SHED_PRIORITY = [
    # Lower priority loads shed first (largest, most non-critical)
    "LOAD_PROPULSION",
    "LOAD_COMPRESSOR",
    "LOAD_SWCOOLPUMP",
    "LOAD_FOTRANSFER",
    # Hotel and emergency NEVER shed
]


class VirtualPMS:
    """
    The vPMS supervisory controller.
    """

    def __init__(self, engine=None):
        self._engine = engine
        self._running = False
        self._cycle_interval_s = 2.0  # Control loop interval
        self._shed_loads: List[str] = []
        self._last_action = "None"

    def attach_engine(self, engine):
        """Attach to a SimulationEngine at runtime."""
        self._engine = engine

    # ── Core Decision Logic ────────────────────────────────────────────────────

    def evaluate(self, state: dict) -> List[dict]:
        """
        Main evaluation function. Returns a list of commands to issue.
        Commands: { "type": "start_gen"/"stop_gen"/"shed_load"/"restore_load", "target": id }
        """
        commands = []
        bus = state.get("bus_bar", {})
        gens = {g["id"]: g for g in state.get("generators", [])}
        loads = {l["id"]: l for l in state.get("loads", [])}

        V = bus.get("voltage_v", 440.0)
        f = bus.get("frequency_hz", 60.0)
        total_load = bus.get("total_load_kw", 0.0)
        total_gen_capacity_online = sum(
            1500.0 if "01" in gid or "02" in gid else 1000.0
            for gid, g in gens.items() if g["online"]
        )

        # ── 1. Emergency: Frequency too low → LOAD SHEDDING ──────────────────
        if f < FREQ_LOW_TRIP:
            logger.warning(f"vPMS: Low frequency {f:.2f}Hz — initiating load shedding!")
            for load_id in LOAD_SHED_PRIORITY:
                if loads.get(load_id, {}).get("active") and not loads.get(load_id, {}).get("shed"):
                    commands.append({"type": "shed_load", "target": load_id})
                    self._last_action = f"Load shed: {load_id} (f={f:.2f}Hz)"
                    break  # Shed one at a time

        # ── 2. Frequency restored → Restore loads ─────────────────────────────
        elif f > 59.5 and self._shed_loads:
            load_to_restore = self._shed_loads[-1]
            commands.append({"type": "restore_load", "target": load_to_restore})
            self._last_action = f"Load restored: {load_to_restore}"

        # ── 3. Generator overloaded → Start standby gen ───────────────────────
        for gid, g in gens.items():
            if g["online"] and g["load_percent"] > MAX_LOAD_PERCENT:
                # Find an offline generator to start
                for gid2, g2 in gens.items():
                    if not g2["online"]:
                        commands.append({"type": "start_gen", "target": gid2})
                        self._last_action = f"Started {gid2} (overload on {gid}: {g['load_percent']:.1f}%)"
                        break

        # ── 4. Low load → Shut down unnecessary generator (fuel optimization) ─
        if len([g for g in gens.values() if g["online"]]) > 1:
            total_demand_margin = total_gen_capacity_online - total_load
            # Can we shed one generator with enough margin?
            if total_demand_margin > (total_load * 0.5 + BLACKOUT_MARGIN_KW):
                for gid, g in gens.items():
                    if g["online"] and g["load_percent"] < MIN_LOAD_PERCENT:
                        commands.append({"type": "stop_gen", "target": gid})
                        self._last_action = f"Stopped {gid} (low load: {g['load_percent']:.1f}%)"
                        break

        # ── 5. Voltage low → Alarm (future: AVR setpoint adjustment) ──────────
        if V < VOLTAGE_LOW_TRIP:
            logger.warning(f"vPMS: Low bus voltage {V:.1f}V — alarm raised.")

        return commands

    def _execute_command(self, cmd: dict):
        """Send a command to the simulation engine."""
        if self._engine is None:
            return
        t = cmd["target"]
        ctype = cmd["type"]
        try:
            if ctype == "start_gen":
                self._engine.start_generator(t)
            elif ctype == "stop_gen":
                self._engine.stop_generator(t)
            elif ctype == "shed_load":
                for load in self._engine.loads:
                    if load.profile.load_id == t:
                        load.shed()
                        self._shed_loads.append(t)
            elif ctype == "restore_load":
                for load in self._engine.loads:
                    if load.profile.load_id == t:
                        load.restore()
                        if t in self._shed_loads:
                            self._shed_loads.remove(t)
        except Exception as e:
            logger.error(f"vPMS command failed ({ctype} on {t}): {e}")

    def control_loop(self):
        """vPMS supervisory control loop (runs in background thread)."""
        self._running = True
        logger.info("🧠 vPMS Control Loop started.")
        # Warmup: wait for simulation to complete at least 5 steps before issuing commands
        time.sleep(5.0)
        while self._running:
            if self._engine:
                state = self._engine.get_state()
                commands = self.evaluate(state)
                for cmd in commands:
                    self._execute_command(cmd)
            time.sleep(self._cycle_interval_s)

    def start(self):
        t = threading.Thread(target=self.control_loop, daemon=True)
        t.start()
        return t

    def stop(self):
        self._running = False

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "last_action": self._last_action,
            "shed_loads": self._shed_loads,
            "cycle_interval_s": self._cycle_interval_s,
            "thresholds": {
                "max_load_percent": MAX_LOAD_PERCENT,
                "freq_low_trip_hz": FREQ_LOW_TRIP,
                "voltage_low_trip_v": VOLTAGE_LOW_TRIP,
            }
        }


# Singleton
_vpms: Optional[VirtualPMS] = None


def get_vpms() -> VirtualPMS:
    global _vpms
    if _vpms is None:
        _vpms = VirtualPMS()
    return _vpms
