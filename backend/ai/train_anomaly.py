"""
Training Script for the LSTM Autoencoder Anomaly Detector.

Workflow:
  1. Run simulation in fast mode (no realtime) to generate baseline data.
  2. Train the autoencoder on NORMAL data only.
  3. Evaluate on held-out fault data to validate detection capability.
  4. Save model + threshold checkpoint.
"""

import sys
import os
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split
import logging
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.autoencoder import LSTMAutoencoder, extract_features, SEQUENCE_LEN, N_FEATURES
from data.synthetic_generator import SyntheticDataGenerator, snapshot_to_dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Hyperparameters ────────────────────────────────────────────────────────────
BATCH_SIZE = 64
EPOCHS = 50
LR = 1e-3
PATIENCE = 7           # Early stopping patience
ANOMALY_PERCENTILE = 97  # Set threshold at 97th percentile of normal training errors

OUTPUT_DIR = Path(__file__).parent.parent / "models"
OUTPUT_DIR.mkdir(exist_ok=True)


def generate_training_data(n_normal: int = 5000, n_fault: int = 1000):
    """
    Generate synthetic normal and fault sequences using the SyntheticDataGenerator.
    Returns: (normal_windows, fault_windows, fault_labels)
    """
    logger.info(f"Generating {n_normal} normal + {n_fault} fault data points...")
    gen = SyntheticDataGenerator(seed=42)

    # Normal data
    normal_features = []
    for snap in gen.generate_stream(duration_seconds=n_normal, fault_probability=0.0):
        snap_dict = {
            "bus_bar": {
                "voltage_v": snap.bus_bar.voltage_v,
                "frequency_hz": snap.bus_bar.frequency_hz,
                "total_load_kw": snap.bus_bar.total_load_kw,
                "power_imbalance_kw": 0.0,
            },
            "generators": [
                {"id": g.id, "load_percent": g.load_percent, "temperature_c": g.temperature_c, "current_a": g.current_a}
                for g in snap.generators
            ]
        }
        normal_features.append(_extract_from_synthetic(snap))

    # Fault data
    fault_features = []
    fault_labels = []
    for snap in gen.generate_stream(duration_seconds=n_fault, fault_probability=0.5):
        fault_features.append(_extract_from_synthetic(snap))
        fault_labels.append(1 if snap.scenario != "normal" else 0)

    return np.array(normal_features), np.array(fault_features), np.array(fault_labels)


def _extract_from_synthetic(snap) -> np.ndarray:
    """Extract feature vector directly from a ShipboardGridSnapshot."""
    g1 = next((g for g in snap.generators if g.id == "GEN_01"), None)
    g2 = next((g for g in snap.generators if g.id == "GEN_02"), None)

    return np.array([
        snap.bus_bar.voltage_v / 440.0,
        snap.bus_bar.frequency_hz / 60.0,
        (g1.load_percent if g1 else 0.0) / 100.0,
        (g2.load_percent if g2 else 0.0) / 100.0,
        (g1.temperature_c if g1 else 80.0) / 150.0,
        (g2.temperature_c if g2 else 80.0) / 150.0,
        (g1.current_a if g1 else 0.0) / 2000.0,
        (g2.current_a if g2 else 0.0) / 2000.0,
        snap.bus_bar.total_load_kw / 4000.0,
        0.0,  # power_imbalance not in synthetic generator
    ], dtype=np.float32)


def build_sequences(features: np.ndarray, seq_len: int = SEQUENCE_LEN) -> np.ndarray:
    """Convert flat feature array into sliding windows."""
    windows = []
    for i in range(len(features) - seq_len):
        windows.append(features[i:i + seq_len])
    return np.array(windows)


def train():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Training on: {device}")

    # ── Data ──────────────────────────────────────────────────────────────────
    normal_feat, fault_feat, fault_labels = generate_training_data(n_normal=4000, n_fault=1000)

    X_normal = build_sequences(normal_feat)  # (N, seq_len, n_features)
    X_fault = build_sequences(fault_feat)
    y_fault = fault_labels[SEQUENCE_LEN:]

    logger.info(f"Normal sequences: {X_normal.shape}, Fault sequences: {X_fault.shape}")

    X_tensor = torch.tensor(X_normal, dtype=torch.float32)
    dataset = TensorDataset(X_tensor, X_tensor)

    n_val = int(len(dataset) * 0.15)
    n_train = len(dataset) - n_val
    train_ds, val_ds = random_split(dataset, [n_train, n_val])

    train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=BATCH_SIZE)

    # ── Model ─────────────────────────────────────────────────────────────────
    model = LSTMAutoencoder(n_features=N_FEATURES, seq_len=SEQUENCE_LEN).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-5)
    criterion = nn.MSELoss()
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5)

    best_val_loss = float("inf")
    patience_counter = 0
    train_history = []

    # ── Training Loop ─────────────────────────────────────────────────────────
    logger.info("Starting training...")
    for epoch in range(1, EPOCHS + 1):
        model.train()
        train_loss = 0.0
        for xb, yb in train_dl:
            xb = xb.to(device)
            optimizer.zero_grad()
            x_hat = model(xb)
            loss = criterion(x_hat, xb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item() * len(xb)
        train_loss /= n_train

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for xb, _ in val_dl:
                xb = xb.to(device)
                x_hat = model(xb)
                val_loss += criterion(x_hat, xb).item() * len(xb)
        val_loss /= n_val

        scheduler.step(val_loss)
        train_history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})

        if epoch % 5 == 0 or epoch == 1:
            logger.info(f"Epoch {epoch:3d}/{EPOCHS} | Train: {train_loss:.6f} | Val: {val_loss:.6f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save({"model_state": model.state_dict()}, OUTPUT_DIR / "autoencoder_best.pt")
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= PATIENCE:
                logger.info(f"Early stopping at epoch {epoch}.")
                break

    # ── Threshold Calibration ─────────────────────────────────────────────────
    logger.info("Calibrating anomaly threshold on normal validation data...")
    checkpoint = torch.load(OUTPUT_DIR / "autoencoder_best.pt", map_location=device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    normal_errors = []
    with torch.no_grad():
        for xb, _ in val_dl:
            xb = xb.to(device)
            err = model.reconstruction_error(xb)
            normal_errors.extend(err.cpu().numpy().tolist())

    threshold = float(np.percentile(normal_errors, ANOMALY_PERCENTILE))
    logger.info(f"✅ Anomaly threshold set at {ANOMALY_PERCENTILE}th percentile: {threshold:.6f}")

    # ── Evaluate on Fault Data ────────────────────────────────────────────────
    logger.info("Evaluating on fault data...")
    X_fault_t = torch.tensor(X_fault, dtype=torch.float32).to(device)
    with torch.no_grad():
        fault_errors = model.reconstruction_error(X_fault_t).cpu().numpy()

    n_faults_true = y_fault.sum()
    detected = np.sum(fault_errors[y_fault == 1] > threshold)
    false_pos = np.sum(fault_errors[y_fault == 0] > threshold)
    detection_rate = detected / max(n_faults_true, 1)
    logger.info(f"Detection Rate: {detection_rate * 100:.1f}% | False Positives: {false_pos}")

    # ── Save Final Checkpoint ─────────────────────────────────────────────────
    final_checkpoint = {
        "model_state": model.state_dict(),
        "threshold": threshold,
        "train_history": train_history,
        "detection_rate": detection_rate,
        "n_features": N_FEATURES,
        "seq_len": SEQUENCE_LEN,
    }
    torch.save(final_checkpoint, OUTPUT_DIR / "autoencoder_final.pt")
    with open(OUTPUT_DIR / "training_log.json", "w") as f:
        json.dump({"history": train_history, "threshold": threshold, "detection_rate": detection_rate}, f, indent=2)

    logger.info(f"✅ Model saved to {OUTPUT_DIR / 'autoencoder_final.pt'}")
    return threshold, detection_rate


if __name__ == "__main__":
    train()
