"""
Synthetic Data Generator for Shipboard Power Systems.
Generates realistic electrical parameters (voltage, current, frequency, load)
for a multi-generator, multi-load shipboard electrical grid.
"""

import numpy as np
import random
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json


@dataclass
class GeneratorState:
    id: str
    online: bool
    voltage_v: float       # Volts (nominal 440V)
    frequency_hz: float    # Hz (nominal 60Hz)
    active_power_kw: float # Kilowatts
    reactive_power_kvar: float
    current_a: float
    fuel_rate_lph: float   # Liters per hour
    temperature_c: float   # Engine temperature in Celsius
    load_percent: float    # Load percentage (0-100)


@dataclass
class LoadState:
    id: str
    name: str
    active: bool
    power_kw: float
    current_a: float
    power_factor: float


@dataclass
class BusBarState:
    id: str
    voltage_v: float
    frequency_hz: float
    total_load_kw: float
    generators_online: int


@dataclass
class ShipboardGridSnapshot:
    timestamp: float
    scenario: str          # "normal", "fault_overload", "fault_voltage_dip", "fault_short_circuit", "fault_freq_deviation"
    generators: List[GeneratorState]
    loads: List[LoadState]
    bus_bar: BusBarState
    anomaly_score: float   # 0.0 = normal, 1.0 = severe fault
    fault_component: Optional[str] = None


class SyntheticDataGenerator:
    """
    Generates synthetic time-series data for a simplified 3-generator,
    6-load shipboard grid. Includes normal operation and injected fault scenarios.
    """

    NOMINAL_VOLTAGE = 440.0   # Volts
    NOMINAL_FREQ = 60.0        # Hz
    GEN_CAPACITY_KW = [1500.0, 1500.0, 1000.0]  # Individual generator capacities

    LOAD_PROFILES = [
        {"id": "LOAD_PROPULSION", "name": "Main Propulsion Motor", "base_kw": 800.0, "pf": 0.85},
        {"id": "LOAD_HOTEL", "name": "Hotel Loads (HVAC, Lighting)", "base_kw": 250.0, "pf": 0.92},
        {"id": "LOAD_PUMP_1", "name": "Sea Water Cooling Pump", "base_kw": 75.0, "pf": 0.88},
        {"id": "LOAD_PUMP_2", "name": "Fuel Oil Transfer Pump", "base_kw": 45.0, "pf": 0.88},
        {"id": "LOAD_COMPRESSOR", "name": "Air Compressor", "base_kw": 120.0, "pf": 0.80},
        {"id": "LOAD_EMERGENCY", "name": "Emergency Systems", "base_kw": 30.0, "pf": 0.95},
    ]

    def __init__(self, seed: int = 42):
        np.random.seed(seed)
        random.seed(seed)

    def _add_gaussian_noise(self, value: float, std_frac: float = 0.005) -> float:
        """Add realistic Gaussian sensor noise."""
        return value + np.random.normal(0, abs(value) * std_frac)

    def generate_normal_snapshot(self, t: float) -> ShipboardGridSnapshot:
        """Generate a snapshot under normal operating conditions."""
        # Simulate daily load cycle with a slow sine wave
        load_cycle = 0.65 + 0.20 * np.sin(2 * np.pi * t / 3600) + 0.05 * np.sin(2 * np.pi * t / 900)

        total_load_kw = sum(p["base_kw"] for p in self.LOAD_PROFILES) * load_cycle

        # Two generators online sharing load proportionally
        gen1_load = min(total_load_kw * 0.55, self.GEN_CAPACITY_KW[0])
        gen2_load = min(total_load_kw * 0.45, self.GEN_CAPACITY_KW[1])

        generators = [
            GeneratorState(
                id="GEN_01",
                online=True,
                voltage_v=self._add_gaussian_noise(self.NOMINAL_VOLTAGE),
                frequency_hz=self._add_gaussian_noise(self.NOMINAL_FREQ, 0.002),
                active_power_kw=self._add_gaussian_noise(gen1_load),
                reactive_power_kvar=self._add_gaussian_noise(gen1_load * 0.32),
                current_a=self._add_gaussian_noise(gen1_load * 1000 / (self.NOMINAL_VOLTAGE * 1.732)),
                fuel_rate_lph=self._add_gaussian_noise(gen1_load * 0.21),
                temperature_c=self._add_gaussian_noise(85.0 + gen1_load / 50),
                load_percent=self._add_gaussian_noise((gen1_load / self.GEN_CAPACITY_KW[0]) * 100),
            ),
            GeneratorState(
                id="GEN_02",
                online=True,
                voltage_v=self._add_gaussian_noise(self.NOMINAL_VOLTAGE),
                frequency_hz=self._add_gaussian_noise(self.NOMINAL_FREQ, 0.002),
                active_power_kw=self._add_gaussian_noise(gen2_load),
                reactive_power_kvar=self._add_gaussian_noise(gen2_load * 0.30),
                current_a=self._add_gaussian_noise(gen2_load * 1000 / (self.NOMINAL_VOLTAGE * 1.732)),
                fuel_rate_lph=self._add_gaussian_noise(gen2_load * 0.21),
                temperature_c=self._add_gaussian_noise(83.0 + gen2_load / 50),
                load_percent=self._add_gaussian_noise((gen2_load / self.GEN_CAPACITY_KW[1]) * 100),
            ),
            GeneratorState(
                id="GEN_03",
                online=False,
                voltage_v=0.0, frequency_hz=0.0, active_power_kw=0.0,
                reactive_power_kvar=0.0, current_a=0.0, fuel_rate_lph=0.0,
                temperature_c=self._add_gaussian_noise(35.0),
                load_percent=0.0,
            ),
        ]

        loads = [
            LoadState(
                id=lp["id"], name=lp["name"], active=True,
                power_kw=self._add_gaussian_noise(lp["base_kw"] * load_cycle),
                current_a=self._add_gaussian_noise(lp["base_kw"] * load_cycle * 1000 / (self.NOMINAL_VOLTAGE * lp["pf"] * 1.732)),
                power_factor=self._add_gaussian_noise(lp["pf"], 0.005),
            )
            for lp in self.LOAD_PROFILES
        ]

        bus_bar = BusBarState(
            id="MAIN_BUS",
            voltage_v=self._add_gaussian_noise(self.NOMINAL_VOLTAGE),
            frequency_hz=self._add_gaussian_noise(self.NOMINAL_FREQ, 0.002),
            total_load_kw=total_load_kw,
            generators_online=2,
        )

        return ShipboardGridSnapshot(
            timestamp=t, scenario="normal",
            generators=generators, loads=loads, bus_bar=bus_bar,
            anomaly_score=self._add_gaussian_noise(0.05, 0.1),
        )

    def inject_overload_fault(self, t: float, base: ShipboardGridSnapshot) -> ShipboardGridSnapshot:
        """Simulate a sudden load spike causing generator overload."""
        spike = 1.8
        snap = self.generate_normal_snapshot(t)
        snap.scenario = "fault_overload"
        snap.bus_bar.total_load_kw *= spike
        snap.bus_bar.frequency_hz = self.NOMINAL_FREQ - random.uniform(2.5, 4.5)
        snap.bus_bar.voltage_v = self.NOMINAL_VOLTAGE * random.uniform(0.82, 0.90)
        snap.generators[0].load_percent = min(105, snap.generators[0].load_percent * spike)
        snap.generators[0].temperature_c += random.uniform(15, 35)
        snap.generators[0].frequency_hz = self.NOMINAL_FREQ - random.uniform(2, 4)
        snap.anomaly_score = random.uniform(0.75, 0.95)
        snap.fault_component = "GEN_01"
        return snap

    def inject_voltage_dip(self, t: float, base: ShipboardGridSnapshot) -> ShipboardGridSnapshot:
        """Simulate a sustained voltage dip on the main bus."""
        snap = self.generate_normal_snapshot(t)
        snap.scenario = "fault_voltage_dip"
        dip_factor = random.uniform(0.70, 0.85)
        snap.bus_bar.voltage_v = self.NOMINAL_VOLTAGE * dip_factor
        for gen in snap.generators:
            if gen.online:
                gen.voltage_v = self.NOMINAL_VOLTAGE * dip_factor
                gen.current_a *= (1.0 / dip_factor)  # Current rises to maintain power
        snap.anomaly_score = random.uniform(0.60, 0.85)
        snap.fault_component = "MAIN_BUS"
        return snap

    def inject_short_circuit(self, t: float, base: ShipboardGridSnapshot) -> ShipboardGridSnapshot:
        """Simulate a short circuit on a load feeder (catastrophic fault)."""
        snap = self.generate_normal_snapshot(t)
        snap.scenario = "fault_short_circuit"
        snap.bus_bar.voltage_v = self.NOMINAL_VOLTAGE * random.uniform(0.1, 0.35)
        snap.bus_bar.frequency_hz = self.NOMINAL_FREQ - random.uniform(5, 10)
        for gen in snap.generators:
            if gen.online:
                gen.current_a *= random.uniform(5, 10)
                gen.voltage_v = snap.bus_bar.voltage_v
                gen.temperature_c += random.uniform(40, 80)
                gen.load_percent = min(150, gen.load_percent * random.uniform(4, 8))
        snap.anomaly_score = random.uniform(0.90, 1.0)
        snap.fault_component = "LOAD_PROPULSION"
        return snap

    def inject_frequency_deviation(self, t: float, base: ShipboardGridSnapshot) -> ShipboardGridSnapshot:
        """Simulate a governor fault causing frequency deviation."""
        snap = self.generate_normal_snapshot(t)
        snap.scenario = "fault_freq_deviation"
        deviation = random.choice([-1, 1]) * random.uniform(3, 7)
        snap.bus_bar.frequency_hz = self.NOMINAL_FREQ + deviation
        snap.generators[0].frequency_hz = self.NOMINAL_FREQ + deviation
        snap.anomaly_score = random.uniform(0.55, 0.80)
        snap.fault_component = "GEN_01"
        return snap

    def generate_stream(self, duration_seconds: int = 600, fault_probability: float = 0.15):
        """
        Generate a continuous stream of grid snapshots.
        Faults are injected randomly based on fault_probability.
        """
        t = 0.0
        dt = 1.0  # 1 second time steps
        fault_types = [
            self.inject_overload_fault,
            self.inject_voltage_dip,
            self.inject_short_circuit,
            self.inject_frequency_deviation,
        ]
        current_fault = None
        fault_duration = 0

        while t < duration_seconds:
            base = self.generate_normal_snapshot(t)

            if fault_duration > 0:
                snapshot = current_fault(t, base)
                fault_duration -= 1
            elif random.random() < fault_probability:
                current_fault = random.choice(fault_types)
                fault_duration = random.randint(5, 30)
                snapshot = current_fault(t, base)
            else:
                snapshot = base

            yield snapshot
            t += dt


def snapshot_to_dict(snap: ShipboardGridSnapshot) -> dict:
    """Convert a snapshot to a JSON-serializable dict."""
    d = {
        "timestamp": snap.timestamp,
        "scenario": snap.scenario,
        "anomaly_score": round(snap.anomaly_score, 4),
        "fault_component": snap.fault_component,
        "bus_bar": asdict(snap.bus_bar),
        "generators": [asdict(g) for g in snap.generators],
        "loads": [asdict(l) for l in snap.loads],
    }
    return d


if __name__ == "__main__":
    gen = SyntheticDataGenerator()
    print("Generating 10 sample snapshots...\n")
    for i, snap in enumerate(gen.generate_stream(duration_seconds=10)):
        print(f"t={snap.timestamp:.1f}s | scenario={snap.scenario:<25} | bus_v={snap.bus_bar.voltage_v:.1f}V | bus_f={snap.bus_bar.frequency_hz:.2f}Hz | anomaly={snap.anomaly_score:.3f}")
