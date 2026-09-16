"""
Diesel Generator Physics Model.

Models the dynamic behavior of a marine diesel generator using
differential equations (AVR + Governor dynamics).

State Variables:
  - E_fd: Field voltage (AVR output)
  - omega: Rotor angular velocity (rad/s)
  - delta: Power angle (rad)
  - P_m: Mechanical power output
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GeneratorParams:
    """
    Physical parameters for a marine diesel generator.
    Default values approximate a 1500 kW, 440V, 60Hz, 4-pole machine.
    """
    # Rating
    rated_kw: float = 1500.0
    rated_voltage_v: float = 440.0
    rated_freq_hz: float = 60.0
    rated_rpm: float = 1800.0  # 4-pole, 60Hz: 120f/P = 1800

    # Synchronous machine parameters (per-unit)
    Xd: float = 1.2   # Direct-axis synchronous reactance
    Xq: float = 0.8   # Quadrature-axis synchronous reactance
    Xd_prime: float = 0.2  # Transient reactance
    Ra: float = 0.01  # Armature resistance

    # Governor parameters
    M: float = 0.15   # Mechanical inertia constant (seconds)
    D: float = 0.05   # Damping coefficient
    Tm: float = 0.5   # Governor mechanical time constant

    # AVR parameters
    Ka: float = 5.0   # Amplifier gain (lowered for Euler stability)
    Ta: float = 0.05  # Amplifier time constant
    Ke: float = 1.0   # Exciter gain
    Te: float = 0.5   # Exciter time constant

    # Fuel / Thermal
    fuel_rate_base_lph: float = 300.0  # Liters/hour at full load
    thermal_time_constant: float = 120.0  # seconds
    base_temp_c: float = 80.0


class DieselGenerator:
    """
    A physics-based model of a marine diesel generator.
    Uses Euler integration to step through time.
    """

    def __init__(self, gen_id: str, params: Optional[GeneratorParams] = None):
        self.gen_id = gen_id
        self.p = params or GeneratorParams()
        self._online = False
        self.active_fault: Optional[str] = None
        self.fault_magnitude: float = 0.0

        # State variables
        self.omega_ref = 2 * np.pi * self.p.rated_freq_hz  # Nominal rad/s
        self.omega = self.omega_ref
        self.delta = 0.0            # Power angle
        self.P_m = 0.0              # Mechanical power (kW)
        self.E_fd = self.p.rated_voltage_v  # Field voltage
        self.V_t = self.p.rated_voltage_v  # Terminal voltage
        self.temperature_c = 35.0  # Cold start temperature

        # Outputs
        self.P_e = 0.0      # Electrical power output (kW)
        self.Q_e = 0.0      # Reactive power (kVAR)
        self.I_a = 0.0      # Armature current (A)
        self.load_percent = 0.0
        self.fuel_rate_lph = 0.0
        self.frequency_hz = self.p.rated_freq_hz

    @property
    def online(self) -> bool:
        return self._online

    def start(self):
        """Bring generator online. Initializes state to nominal."""
        self._online = True
        self.omega = self.omega_ref
        self.V_t = self.p.rated_voltage_v
        self.E_fd = self.p.rated_voltage_v
        self.P_m = 0.0
        self.P_e = 0.0
        self.I_a = 0.0   # Reset current on startup to avoid stale phantom current
        self.Q_e = 0.0

    def stop(self):
        """Take generator offline."""
        self._online = False
        self.omega = 0.0
        self.P_m = 0.0
        self.P_e = 0.0
        self.I_a = 0.0
        self.Q_e = 0.0

    def apply_fault(self, fault_type: str, magnitude: float = 1.0):
        """
        Inject a fault into the generator model.
        fault_type: 'overload', 'short_circuit', 'governor_loss', 'avr_failure'
        magnitude: 0.0 to 1.0, severity
        """
        self.active_fault = fault_type
        self.fault_magnitude = magnitude

    def clear_fault(self):
        self.active_fault = None
        self.fault_magnitude = 0.0

    def step(self, dt: float, load_demand_kw: float, V_bus: float, noise_std: float = 0.005):
        """
        Advance the generator state by dt seconds.

        Args:
            dt: Time step in seconds
            load_demand_kw: Electrical load demanded from this generator
            V_bus: Bus voltage to synchronize against
            noise_std: Gaussian noise fraction for sensor realism
        """
        if not self._online:
            self.frequency_hz = 0.0
            self.V_t = 0.0
            self.P_e = 0.0
            self.P_m = 0.0
            self.I_a = 0.0   # CRITICAL: zero current when offline prevents phantom bus voltage drop
            self.Q_e = 0.0
            self.temperature_c = max(35.0, self.temperature_c - dt * 0.1)
            return

        # ── Electrical Output ──────────────────────────────────────────────────
        self.P_e = load_demand_kw
        self.Q_e = self.P_e * np.tan(np.arccos(0.85))  # Assume PF = 0.85

        # ── Governor (Swing Equation) ─────────────────────────────────────────
        # dp/dt = (P_m - P_e - D*(omega - omega_ref)) / M
        P_e_target = np.clip(load_demand_kw, 0, self.p.rated_kw * 1.3)

        # Governor: slowly move P_m toward demanded electrical power
        dPm_dt = (P_e_target - self.P_m) / self.p.Tm
        self.P_m += dPm_dt * dt
        self.P_m = np.clip(self.P_m, 0, self.p.rated_kw * 1.3)

        if self.active_fault == "overload":
            self.P_m = self.p.rated_kw * (1.0 + self.fault_magnitude * 0.5)
            # Overload also heats up the machine faster
            self.temperature_c = min(self.temperature_c + 0.5, 150.0)
            # Overload causes frequency droop
            omega_sync = self.p.rated_rpm * 2 * np.pi / 60.0
            self.omega_ref = omega_sync * (1.0 - self.fault_magnitude * 0.05)

        # Swing equation for rotor speed
        domega_dt = (self.P_m - self.P_e - self.p.D * (self.omega - self.omega_ref)) / self.p.M
        self.omega += domega_dt * dt
        
        if self.active_fault == "governor_loss":
            self.omega = self.omega_ref * (1.0 + self.fault_magnitude * 0.1)
            
        self.omega = np.clip(self.omega, self.omega_ref * 0.5, self.omega_ref * 1.2)

        # ── AVR (Voltage Regulator) ────────────────────────────────────────────
        V_err = self.p.rated_voltage_v - self.V_t
        dEfd_dt = (self.p.Ka * V_err - self.E_fd) / self.p.Te
        self.E_fd += dEfd_dt * dt
        
        if self.active_fault == "avr_failure":
            # Stronger effect: 0.6 multiplier causes bigger voltage dip the AI can see
            self.E_fd = self.p.rated_voltage_v * (1.0 - self.fault_magnitude * 0.6)
            
        self.E_fd = np.clip(self.E_fd, 0, self.p.rated_voltage_v * 1.5)

        # Terminal voltage approximation
        self.V_t = self.E_fd - self.p.Ra * (self.P_m / (self.p.rated_voltage_v + 1e-9))
        self.V_t = np.clip(self.V_t, 0, self.p.rated_voltage_v * 1.2)
        
        if self.active_fault == "avr_failure":
             # Force terminal voltage down significantly
             self.V_t = self.V_t * (1.0 - self.fault_magnitude * 0.4)

        if self.active_fault == "short_circuit":
            self.V_t = self.V_t * (1.0 - self.fault_magnitude * 0.9)

        S = np.sqrt(self.P_e**2 + self.Q_e**2)
        # Use rated voltage in denominator, not V_t — V_t can collapse to ~0 during
        # transients, causing unrealistic phantom currents that corrupt the bus model
        V_denom = max(self.p.rated_voltage_v * 0.5, self.V_t)  # Never below 50% nominal
        self.I_a = (S * 1000) / (np.sqrt(3) * V_denom)
        # Cap at 3x rated current (covers even severe short circuits)
        rated_current = (self.p.rated_kw * 1000) / (np.sqrt(3) * self.p.rated_voltage_v * 0.85)
        self.I_a = np.clip(self.I_a, 0.0, rated_current * 3.0)

        if self.active_fault == "short_circuit":
            self.I_a = min(self.I_a * (1.0 + self.fault_magnitude * 5), rated_current * 3.0)

        # ── Derived Quantities ─────────────────────────────────────────────────
        self.frequency_hz = self.omega / (2 * np.pi)
        self.load_percent = (self.P_e / self.p.rated_kw) * 100.0

        # Thermal model: temperature rises with load
        T_steady = self.p.base_temp_c + 50.0 * (self.load_percent / 100.0)
        dT_dt = (T_steady - self.temperature_c) / self.p.thermal_time_constant
        self.temperature_c += dT_dt * dt

        # Fuel consumption (Willans line approximation)
        self.fuel_rate_lph = self.p.fuel_rate_base_lph * (0.15 + 0.85 * (self.load_percent / 100.0))

        # Add sensor noise
        if noise_std > 0:
            self.V_t += np.random.normal(0, self.V_t * noise_std)
            self.frequency_hz += np.random.normal(0, self.frequency_hz * noise_std * 0.5)

    def get_state(self) -> dict:
        return {
            "id": self.gen_id,
            "online": self._online,
            "voltage_v": round(self.V_t, 2),
            "frequency_hz": round(self.frequency_hz, 3),
            "active_power_kw": round(self.P_e, 2),
            "reactive_power_kvar": round(self.Q_e, 2),
            "current_a": round(self.I_a, 2),
            "fuel_rate_lph": round(self.fuel_rate_lph, 2),
            "temperature_c": round(self.temperature_c, 2),
            "load_percent": round(self.load_percent, 2),
            "fault_active": self.active_fault is not None,
        }
