"""Debug script to trace exactly what extract_features produces from live state."""
import sys, os, json, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.autoencoder import extract_features, TORCH_AVAILABLE
import numpy as np

state = requests.get("http://localhost:8000/api/state").json()

bus = state.get("bus_bar", {})
gens = state.get("generators", [])
g1 = next((g for g in gens if g["id"] == "GEN_01"), {})
g2 = next((g for g in gens if g["id"] == "GEN_02"), {})

print("=== RAW VALUES ===")
print(f"bus_voltage_v      = {bus.get('voltage_v')}")
print(f"bus_freq_hz        = {bus.get('frequency_hz')}")
print(f"g1 load_percent    = {g1.get('load_percent')}")
print(f"g2 load_percent    = {g2.get('load_percent')}")
print(f"g1 temperature_c   = {g1.get('temperature_c')}")
print(f"g2 temperature_c   = {g2.get('temperature_c')}")
print(f"g1 current_a       = {g1.get('current_a')}")
print(f"g2 current_a       = {g2.get('current_a')}")
print(f"total_load_kw      = {bus.get('total_load_kw')}")
print(f"power_imbalance_kw = {bus.get('power_imbalance_kw')}")

features = extract_features(state)
print("\n=== NORMALIZED FEATURES (must all be in ~[0, 1]) ===")
names = ["bus_voltage", "bus_freq", "g1_load%", "g2_load%", "g1_temp", "g2_temp", "g1_current", "g2_current", "total_load", "imbalance"]
for name, val in zip(names, features):
    flag = "⚠️ OUT OF RANGE" if abs(val) > 2.0 else "✓"
    print(f"  {name:20s} = {val:.6f}  {flag}")

if TORCH_AVAILABLE:
    import torch
    from ai.autoencoder import LSTMAutoencoder, SEQUENCE_LEN
    model = LSTMAutoencoder(seq_len=SEQUENCE_LEN)
    path = os.path.join(os.path.dirname(__file__), "models", "autoencoder_final.pt")
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    # Build a fake window of 30 identical normal frames
    window = np.stack([features] * SEQUENCE_LEN)
    x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        x_hat = model(x)
        err = model.reconstruction_error(x)
    
    print(f"\n=== LSTM SINGLE SNAPSHOT TEST ===")
    print(f"Input  (first frame): {x[0,0].numpy()}")
    print(f"Output (first frame): {x_hat[0,0].numpy()}")
    print(f"Reconstruction Error: {err.item():.8f}")
    print(f"Threshold           : {ckpt.get('threshold', '?')}")
    print(f"Is Anomaly?         : {err.item() > ckpt.get('threshold', 0.0001)}")
