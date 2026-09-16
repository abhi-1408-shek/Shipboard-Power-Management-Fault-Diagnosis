import sys
import os
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app, lifespan

client = TestClient(app)


def test_api_health_check():
    """Validates the API is online and responding."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_simulation_state_endpoint():
    """Validates that the /api/state endpoint returns a properly structured grid snapshot."""
    with TestClient(app) as client_with_lifespan:
        response = client_with_lifespan.get("/api/state")
        assert response.status_code == 200
        
        data = response.json()
        assert "sim_time_s" in data
        assert "bus_bar" in data
        assert "generators" in data
        assert len(data["generators"]) == 3
        
        # At startup, 2 generators are started explicitly, but vPMS might immediately start a 3rd
        online_gens = [g for g in data["generators"] if g["online"]]
        assert len(online_gens) >= 2


def test_fault_injection_endpoint():
    """Validates that we can programmatically inject and list faults via REST."""
    with TestClient(app) as client_with_lifespan:
        # Inject an overload fault
        payload = {
            "component_id": "GEN_01",
            "fault_type": "overload",
            "magnitude": 1.0,
            "duration_s": 10.0
        }
        res_inject = client_with_lifespan.post("/api/fault/inject", json=payload)
        assert res_inject.status_code == 200
        assert res_inject.json()["status"] == "fault_injected"

        # Verify it's active
        res_active = client_with_lifespan.get("/api/faults/active")
        assert res_active.status_code == 200
        faults = res_active.json()["active_faults"]
        assert "GEN_01" in faults
        assert faults["GEN_01"]["fault_type"] == "overload"
        
        # Clear the fault
        res_clear = client_with_lifespan.delete("/api/fault/GEN_01")
        assert res_clear.status_code == 200
        
        # Verify it's cleared
        res_active_after = client_with_lifespan.get("/api/faults/active")
        assert "GEN_01" not in res_active_after.json()["active_faults"]
