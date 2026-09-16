import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.generator import DieselGenerator, GeneratorParams
from simulation.load import LoadProfile, ShipLoad
from simulation.bus_bar import BusBar


def test_generator_droop_control():
    """
    Validates the swing equation: if mechanical power target < electrical load,
    the rotor speed (frequency) must drop.
    """
    gen = DieselGenerator("GEN_TEST", GeneratorParams(rated_kw=1000.0, rated_freq_hz=60.0, M=0.15))
    gen.start()

    # Base state: unloaded, nominal frequency
    assert abs(gen.frequency_hz - 60.0) < 0.1

    # Apply heavy sudden load
    # Initially P_m is 0. P_e goes to 800 instantly.
    # The governor will take time to catch up, so omega (and frequency) should drop.
    dt = 0.1
    gen.step(dt=dt, load_demand_kw=800.0, V_bus=440.0, noise_std=0.0)

    # Frequency should dip below 60.0 due to instantaneous power deficit
    assert gen.frequency_hz < 60.0

    # P_m should start ramping up towards 800
    assert gen.P_m > 0.0
    assert gen.P_m < 800.0


def test_generator_voltage_regulation_avr():
    """
    Validates AVR logic: heavy reactive/active load drops terminal voltage,
    which the AVR must then compensate for by increasing field voltage.
    """
    gen = DieselGenerator("GEN_TEST")
    gen.start()

    # Sudden short circuit (massive current draw, huge voltage drop)
    gen.apply_fault("short_circuit", magnitude=1.0)
    gen.step(dt=0.1, load_demand_kw=1500.0, V_bus=440.0, noise_std=0.0)

    assert gen.V_t < 440.0 * 0.5  # Voltage should collapse
    assert gen.I_a > 3000.0       # Massive fault current

    # Clear fault and wait for AVR recovery
    gen.clear_fault()
    for _ in range(50):
        gen.step(dt=0.1, load_demand_kw=500.0, V_bus=440.0, noise_std=0.0)

    # Voltage should recover near nominal
    assert gen.V_t > 350.0


def test_bus_bar_power_flow():
    """
    Validates that total load is properly distributed across online generators.
    """
    g1 = DieselGenerator("G1", GeneratorParams(rated_kw=1000.0))
    g2 = DieselGenerator("G2", GeneratorParams(rated_kw=1000.0))
    g1.start()
    g2.start()

    load1 = ShipLoad(LoadProfile("L1", "Pump", 400.0, load_type="constant_power"))
    load2 = ShipLoad(LoadProfile("L2", "Hotel", 200.0, load_type="constant_power"))

    bus = BusBar()
    
    # Run a few steps to stabilize
    for _ in range(10):
        bus.solve_power_flow([g1, g2], [load1, load2], dt=0.1)

    # Total load should be ~600 kW
    assert abs(bus.total_load_kw - 600.0) < 15.0

    # Because G1 and G2 have equal capacities (1000kW each), load should split 50/50 (~300kW each)
    assert abs(g1.P_e - 300.0) < 15.0
    assert abs(g2.P_e - 300.0) < 15.0
