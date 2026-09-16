import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulation.generator import DieselGenerator
gen = DieselGenerator("GEN_TEST")
gen.start()
gen.apply_fault("short_circuit", magnitude=1.0)
gen.step(dt=0.1, load_demand_kw=1500.0, V_bus=440.0, noise_std=0.0)
print("DURING FAULT:", gen.V_t, gen.E_fd)
gen.clear_fault()
for i in range(50):
    gen.step(dt=0.1, load_demand_kw=500.0, V_bus=440.0, noise_std=0.0)
    print(f"STEP {i} - V_t:", gen.V_t, "E_fd:", gen.E_fd)
