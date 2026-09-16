"""
Load Model for Shipboard Electrical Consumers.
Models static and dynamic load behaviour (Z, I, P constant power loads).
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class LoadProfile:
    load_id: str
    name: str
    rated_kw: float
    power_factor: float = 0.85
    load_type: str = "constant_power"  # "constant_power", "constant_impedance", "motor"
    # Motor-specific
    inrush_factor: float = 6.0        # Motor starting current factor


class ShipLoad:
    """
    Represents a single shipboard electrical consumer.
    Supports constant-power, constant-impedance, and induction motor loads.
    """

    def __init__(self, profile: LoadProfile):
        self.profile = profile
        self._active = True
        self._shed = False
        self.current_kw = profile.rated_kw
        self.current_a = 0.0
        self.power_factor = profile.power_factor
        self._transient_count = 0

    @property
    def active(self) -> bool:
        return self._active and not self._shed

    def shed(self):
        """vPMS commanded load shedding."""
        self._shed = True

    def restore(self):
        """vPMS commanded load restoration."""
        self._shed = False

    def trip(self):
        """Fault-driven load trip."""
        self._active = False

    def step(self, dt: float, V_bus: float, modulation: float = 1.0):
        """
        Compute load demand given bus voltage and an optional modulation factor.
        modulation: 0.0 = off, 1.0 = full load (for variable loads like propulsion).
        """
        if not self.active:
            self.current_kw = 0.0
            self.current_a = 0.0
            return

        V_nom = 440.0
        V_ratio = V_bus / V_nom if V_nom > 0 else 1.0

        if self.profile.load_type == "constant_power":
            # Ideal constant-power: current rises as voltage drops
            self.current_kw = self.profile.rated_kw * modulation
            self.power_factor = self.profile.power_factor

        elif self.profile.load_type == "constant_impedance":
            # Load drops with V^2 (e.g., heating elements)
            self.current_kw = self.profile.rated_kw * modulation * (V_ratio ** 2)
            self.power_factor = self.profile.power_factor

        elif self.profile.load_type == "motor":
            # During starting (first few steps): inrush current
            if self._transient_count < 5:
                self.current_kw = self.profile.rated_kw * self.profile.inrush_factor * modulation
                self._transient_count += 1
            else:
                self.current_kw = self.profile.rated_kw * modulation * max(0.5, V_ratio)
            self.power_factor = max(0.3, self.profile.power_factor * V_ratio)

        # Add ±2% noise to simulate real load variation
        self.current_kw *= (1 + np.random.normal(0, 0.02))
        self.current_kw = max(0, self.current_kw)

        # Compute current draw
        S_kva = self.current_kw / max(self.power_factor, 0.01)
        self.current_a = (S_kva * 1000) / (np.sqrt(3) * max(V_bus, 1.0))

    def get_state(self) -> dict:
        return {
            "id": self.profile.load_id,
            "name": self.profile.name,
            "active": self.active,
            "shed": self._shed,
            "power_kw": round(self.current_kw, 2),
            "current_a": round(self.current_a, 2),
            "power_factor": round(self.power_factor, 3),
        }


# ── Predefined Ship Load Manifest ─────────────────────────────────────────────

def create_default_loads() -> list:
    """Instantiate the default set of loads for a 4000 DWT vessel."""
    profiles = [
        LoadProfile("LOAD_PROPULSION",  "Main Propulsion Motor",    rated_kw=800.0, power_factor=0.85, load_type="motor"),
        LoadProfile("LOAD_HOTEL",       "Hotel Loads",              rated_kw=250.0, power_factor=0.92, load_type="constant_power"),
        LoadProfile("LOAD_SWCOOLPUMP",  "Sea Water Cooling Pump",   rated_kw=75.0,  power_factor=0.88, load_type="motor"),
        LoadProfile("LOAD_FOTRANSFER",  "Fuel Oil Transfer Pump",   rated_kw=45.0,  power_factor=0.88, load_type="motor"),
        LoadProfile("LOAD_COMPRESSOR",  "Air Compressor",           rated_kw=120.0, power_factor=0.80, load_type="motor"),
        LoadProfile("LOAD_EMERGENCY",   "Emergency Systems",        rated_kw=30.0,  power_factor=0.95, load_type="constant_power"),
    ]
    return [ShipLoad(p) for p in profiles]
