"""
Bus Bar / Network Topology Model.
Represents the main electrical bus that interconnects generators and loads.
Computes power balance and bus voltage using the aggregated power flow.
"""

import numpy as np
from typing import List
from simulation.generator import DieselGenerator
from simulation.load import ShipLoad


class BusBar:
    """
    Single main bus bar model for a radial shipboard power network.
    Implements simplified power-flow (load-flow) for a low-voltage marine grid.
    """

    NOMINAL_VOLTAGE = 440.0  # Volts
    NOMINAL_FREQ = 60.0      # Hz

    def __init__(self, bus_id: str = "MAIN_BUS"):
        self.bus_id = bus_id
        self.V_bus = self.NOMINAL_VOLTAGE
        self.frequency_hz = self.NOMINAL_FREQ
        self.total_generation_kw = 0.0
        self.total_load_kw = 0.0
        self.power_imbalance_kw = 0.0
        self.reactive_generation_kvar = 0.0
        self.generators_online: int = 0

        # Bus impedance (simplified Thevenin equivalent, in Ohms)
        self._R_bus = 0.005
        self._X_bus = 0.02

    def solve_power_flow(
        self,
        generators: List[DieselGenerator],
        loads: List[ShipLoad],
        dt: float,
    ):
        """
        Simplified power balance & bus voltage calculation.

        1. Sum up all load demands.
        2. Distribute load across online generators (proportional to capacity).
        3. Calculate voltage drop from aggregate current.
        4. Update each generator's step with its share.
        5. Update each load's step with the new bus voltage.
        """

        # ── Step 1: Compute total load demand ─────────────────────────────────
        # Use previous bus voltage for load calculation
        total_load_kw = sum(
            load.current_kw for load in loads if load.active
        )
        total_load_kw = max(total_load_kw, 0.0)

        # ── Step 2: Generator load sharing ────────────────────────────────────
        online_gens = [g for g in generators if g.online]
        self.generators_online = len(online_gens)

        if not online_gens:
            # BLACKOUT condition
            self.V_bus = 0.0
            self.frequency_hz = 0.0
            self.total_generation_kw = 0.0
            self.total_load_kw = total_load_kw
            self.power_imbalance_kw = -total_load_kw
            return

        total_capacity = sum(g.p.rated_kw for g in online_gens)
        gen_demands = {
            g.gen_id: (g.p.rated_kw / total_capacity) * total_load_kw
            for g in online_gens
        }

        # ── Step 3: Step each generator ───────────────────────────────────────
        for gen in online_gens:
            gen.step(dt=dt, load_demand_kw=gen_demands[gen.gen_id], V_bus=self.V_bus)

        # ── Step 4: Aggregate generation ──────────────────────────────────────
        self.total_generation_kw = sum(g.P_e for g in online_gens)
        self.reactive_generation_kvar = sum(g.Q_e for g in online_gens)

        # ── Step 5: Power balance & frequency ─────────────────────────────────
        self.power_imbalance_kw = self.total_generation_kw - total_load_kw

        # Frequency deviation proportional to imbalance (droop control approximation)
        droop_gain = 0.002   # Hz per kW imbalance
        freq_deviation = self.power_imbalance_kw * droop_gain
        self.frequency_hz = np.clip(
            self.NOMINAL_FREQ + freq_deviation, 55.0, 65.0
        )

        # ── Step 6: Bus voltage (aggregate droop) ─────────────────────────────
        # Only count current from online generators (offline ones have I_a=0 now, but explicit filter for safety)
        total_current_a = sum(g.I_a for g in online_gens if g.online)
        # Voltage drop across bus impedance (simplified)
        delta_V = total_current_a * self._R_bus * np.sqrt(3)
        self.V_bus = np.clip(
            self.NOMINAL_VOLTAGE - delta_V,
            self.NOMINAL_VOLTAGE * 0.85,   # Tighter bound: min 85% of nominal
            self.NOMINAL_VOLTAGE * 1.1,
        )
        # Add small noise
        self.V_bus += np.random.normal(0, self.V_bus * 0.001)
        self.frequency_hz += np.random.normal(0, 0.005)

        # ── Step 7: Update loads with new bus voltage ─────────────────────────
        for load in loads:
            if load.active:
                load.step(dt=dt, V_bus=self.V_bus)

        self.total_load_kw = sum(l.current_kw for l in loads if l.active)

    def get_state(self) -> dict:
        return {
            "id": self.bus_id,
            "voltage_v": round(self.V_bus, 2),
            "frequency_hz": round(self.frequency_hz, 3),
            "total_generation_kw": round(self.total_generation_kw, 2),
            "total_load_kw": round(self.total_load_kw, 2),
            "power_imbalance_kw": round(self.power_imbalance_kw, 2),
            "reactive_generation_kvar": round(self.reactive_generation_kvar, 2),
            "generators_online": self.generators_online,
        }
