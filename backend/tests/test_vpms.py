import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.vpms import VirtualPMS, MAX_LOAD_PERCENT, FREQ_LOW_TRIP


def test_vpms_n_minus_1_redundancy():
    """
    Validates that if a generator exceeds MAX_LOAD_PERCENT, the vPMS issues
    a 'start_gen' command to an offline generator.
    """
    vpms = VirtualPMS()
    
    # Simulate a state where GEN_01 is overloaded, and GEN_02 is offline.
    state = {
        "bus_bar": {"voltage_v": 440.0, "frequency_hz": 60.0, "total_load_kw": 1400.0},
        "generators": [
            {"id": "GEN_01", "online": True, "load_percent": 95.0}, # Overloaded > 85%
            {"id": "GEN_02", "online": False, "load_percent": 0.0},
            {"id": "GEN_03", "online": False, "load_percent": 0.0},
        ],
        "loads": []
    }

    commands = vpms.evaluate(state)
    
    # Should contain a start_gen command for an offline generator
    start_cmds = [c for c in commands if c["type"] == "start_gen"]
    assert len(start_cmds) == 1
    assert start_cmds[0]["target"] in ["GEN_02", "GEN_03"]


def test_vpms_load_shedding_on_underfrequency():
    """
    Validates that if the frequency drops below the trip threshold (e.g. from a blackout cascade),
    the vPMS immediately issues load shed commands for non-critical loads.
    """
    vpms = VirtualPMS()
    
    # Simulate a severe frequency dip (e.g. 56 Hz)
    state = {
        "bus_bar": {"voltage_v": 410.0, "frequency_hz": FREQ_LOW_TRIP - 1.0, "total_load_kw": 2500.0},
        "generators": [
            {"id": "GEN_01", "online": True, "load_percent": 110.0},
            {"id": "GEN_02", "online": True, "load_percent": 110.0},
        ],
        "loads": [
            {"id": "LOAD_PROPULSION", "active": True, "shed": False}, # Lowest priority, sheds first
            {"id": "LOAD_EMERGENCY", "active": True, "shed": False},  # Critical, never sheds
        ]
    }

    commands = vpms.evaluate(state)
    
    shed_cmds = [c for c in commands if c["type"] == "shed_load"]
    assert len(shed_cmds) > 0
    
    # Should shed the lowest priority load
    assert shed_cmds[0]["target"] == "LOAD_PROPULSION"
    
    # Verify emergency load was NOT shed
    assert not any(c["target"] == "LOAD_EMERGENCY" for c in shed_cmds)
