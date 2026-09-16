"""
Retraining script that generates data by running the actual physics simulation
instead of the synthetic data generator — ensures the training distribution
exactly matches the live inference distribution.
"""
import sys
import os
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split
import logging
from pathlib import Path
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.generator import DieselGenerator, GeneratorParams
from simulation.load import create_default_loads
from simulation.bus_bar import BusBar
from ai.autoencoder import LSTMAutoencoder, extract_features, SEQUENCE_LEN, N_FEATURES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "models"
OUTPUT_DIR.mkdir(exist_ok=True)
BATCH_SIZE = 64
EPOCHS = 60
LR = 1e-3
PATIENCE = 10
ANOMALY_PERCENTILE = 97


def run_sim(steps: int, inject_fault: bool = False) -> list:
    """Run the physics simulation for N steps, return list of state dicts."""
    g1 = DieselGenerator("GEN_01", GeneratorParams(rated_kw=1500.0))
    g2 = DieselGenerator("GEN_02", GeneratorParams(rated_kw=1500.0))
    g1.start(); g2.start()
    loads = create_default_loads()
    bus = BusBar("MAIN_BUS")

    states = []
    dt = 0.5
    for step in range(steps):
        bus.solve_power_flow([g1, g2], loads, dt=dt)

        # Optionally inject faults after warmup
        if inject_fault and step > 50:
            fault_type = ["overload", "short_circuit", "governor_loss", "avr_failure"][step % 4]
            g1.apply_fault(fault_type, magnitude=0.8)
        elif inject_fault:
            g1.clear_fault()

        state = {
            "bus_bar": bus.get_state(),
            "generators": [g1.get_state(), g2.get_state()],
        }
        states.append(state)

    return states


def build_sequences(features, seq_len=SEQUENCE_LEN):
    windows = []
    for i in range(len(features) - seq_len):
        windows.append(features[i:i + seq_len])
    return np.array(windows, dtype=np.float32)


def generate_data(n_normal_steps=6000, n_fault_steps=2000):
    logger.info("Generating data from PHYSICS simulation (not synthetic)...")

    # Normal operation
    logger.info(f"  Running {n_normal_steps} normal simulation steps...")
    normal_states = run_sim(n_normal_steps, inject_fault=False)
    normal_features = [extract_features(s) for s in normal_states]

    # Fault operation
    logger.info(f"  Running {n_fault_steps} fault simulation steps...")
    fault_states = run_sim(n_fault_steps, inject_fault=True)
    fault_features = [extract_features(s) for s in fault_states]
    fault_labels = [1 if i > 50 else 0 for i in range(n_fault_steps)]

    normal_seq = build_sequences(np.array(normal_features))
    fault_seq = build_sequences(np.array(fault_features))
    fault_label_seq = np.array(fault_labels[SEQUENCE_LEN:])

    logger.info(f"Normal sequences: {normal_seq.shape}")
    logger.info(f"Fault sequences: {fault_seq.shape}")
    return normal_seq, fault_seq, fault_label_seq


def train():
    device = torch.device("cpu")
    logger.info(f"Training on: {device}")

    normal_seq, fault_seq, fault_labels = generate_data()

    x_tensor = torch.tensor(normal_seq, dtype=torch.float32)
    dataset = TensorDataset(x_tensor)
    val_size = int(len(dataset) * 0.15)
    train_size = len(dataset) - val_size
    train_ds, val_ds = random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE)

    model = LSTMAutoencoder(seq_len=SEQUENCE_LEN).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
    criterion = nn.MSELoss()

    best_val = float("inf")
    patience_counter = 0
    best_state = None

    logger.info("Starting training...")
    for epoch in range(1, EPOCHS + 1):
        model.train()
        train_losses = []
        for (x_batch,) in train_loader:
            x_batch = x_batch.to(device)
            out = model(x_batch)
            loss = criterion(out, x_batch)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for (x_batch,) in val_loader:
                x_batch = x_batch.to(device)
                out = model(x_batch)
                val_losses.append(criterion(out, x_batch).item())

        train_loss = np.mean(train_losses)
        val_loss = np.mean(val_losses)
        scheduler.step(val_loss)

        if epoch % 5 == 0 or epoch == 1:
            logger.info(f"Epoch {epoch:3d}/{EPOCHS} | Train: {train_loss:.6f} | Val: {val_loss:.6f}")

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= PATIENCE:
                logger.info(f"Early stopping at epoch {epoch}")
                break

    model.load_state_dict(best_state)
    model.eval()

    # Calibrate threshold on validation set
    logger.info("Calibrating anomaly threshold on normal validation data...")
    all_errors = []
    with torch.no_grad():
        for (x_batch,) in val_loader:
            x_batch = x_batch.to(device)
            err = model.reconstruction_error(x_batch)
            all_errors.extend(err.cpu().numpy().tolist())

    threshold = float(np.percentile(all_errors, ANOMALY_PERCENTILE))
    logger.info(f"✅ Threshold at {ANOMALY_PERCENTILE}th percentile: {threshold:.8f}")

    # Evaluate on fault data
    logger.info("Evaluating on fault sequences...")
    fault_tensor = torch.tensor(fault_seq, dtype=torch.float32).to(device)
    with torch.no_grad():
        fault_errors = model.reconstruction_error(fault_tensor).cpu().numpy()

    # Only count fault sequences that are actually labelled as fault
    fault_only_mask = fault_labels == 1
    if fault_only_mask.any():
        detected = (fault_errors[fault_only_mask] > threshold).sum()
        detection_rate = 100.0 * detected / fault_only_mask.sum()
        logger.info(f"Detection Rate on labelled faults: {detection_rate:.1f}%")
    
    normal_detections = (np.array(all_errors) > threshold).sum()
    logger.info(f"False Positives on normal data: {normal_detections}/{len(all_errors)} ({100*normal_detections/len(all_errors):.1f}%)")

    path = OUTPUT_DIR / "autoencoder_final.pt"
    torch.save({"model_state": model.state_dict(), "threshold": threshold}, path)
    logger.info(f"✅ Model saved to {path}")


if __name__ == "__main__":
    train()
