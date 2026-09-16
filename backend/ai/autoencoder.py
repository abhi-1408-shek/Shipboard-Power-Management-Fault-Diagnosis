"""
LSTM Autoencoder for Anomaly Detection in Shipboard Power Systems.

Architecture:
  - Input: Multivariate time-series window (sequence of grid feature vectors)
  - Encoder: LSTM → compresses to latent representation
  - Decoder: LSTM → reconstructs the input window
  - Anomaly Score: Mean Squared Error of reconstruction
    (high MSE = likely anomaly)

Features used per timestep:
  [bus_voltage, bus_freq, gen1_load%, gen2_load%, gen1_temp, gen2_temp,
   gen1_current, gen2_current, total_load_kw, power_imbalance]

Fallback: If PyTorch is not installed, a z-score based statistical detector
is used instead (no model files required).
"""

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None

import numpy as np
from typing import List, Tuple, Optional


FEATURE_NAMES = [
    "bus_voltage",
    "bus_freq",
    "gen1_load_pct",
    "gen2_load_pct",
    "gen1_temp",
    "gen2_temp",
    "gen1_current",
    "gen2_current",
    "total_load_kw",
    "power_imbalance_kw",
]

N_FEATURES = len(FEATURE_NAMES)
SEQUENCE_LEN = 30     # 30 seconds of history at 1s resolution
LATENT_DIM = 16
HIDDEN_DIM = 64


# ── Model Definition (only if PyTorch is available) ────────────────────────────

if TORCH_AVAILABLE:
    class LSTMEncoder(nn.Module):
        def __init__(self, n_features: int, hidden_dim: int, latent_dim: int):
            super().__init__()
            self.lstm = nn.LSTM(n_features, hidden_dim, num_layers=2, batch_first=True, dropout=0.1)
            self.fc = nn.Linear(hidden_dim, latent_dim)

        def forward(self, x):
            out, (h_n, c_n) = self.lstm(x)
            z = self.fc(h_n[-1])
            return z, (h_n, c_n)

    class LSTMDecoder(nn.Module):
        def __init__(self, n_features: int, hidden_dim: int, latent_dim: int, seq_len: int):
            super().__init__()
            self.seq_len = seq_len
            self.fc = nn.Linear(latent_dim, hidden_dim)
            self.lstm = nn.LSTM(hidden_dim, hidden_dim, num_layers=2, batch_first=True, dropout=0.1)
            self.output_layer = nn.Linear(hidden_dim, n_features)

        def forward(self, z):
            h = self.fc(z)
            h = h.unsqueeze(1).repeat(1, self.seq_len, 1)
            out, _ = self.lstm(h)
            return self.output_layer(out)

    class LSTMAutoencoder(nn.Module):
        """Full LSTM Autoencoder for anomaly detection."""

        def __init__(self, n_features=N_FEATURES, hidden_dim=HIDDEN_DIM, latent_dim=LATENT_DIM, seq_len=SEQUENCE_LEN):
            super().__init__()
            self.encoder = LSTMEncoder(n_features, hidden_dim, latent_dim)
            self.decoder = LSTMDecoder(n_features, hidden_dim, latent_dim, seq_len)
            self.seq_len = seq_len
            self.n_features = n_features

        def forward(self, x):
            z, _ = self.encoder(x)
            return self.decoder(z)

        def reconstruction_error(self, x):
            """Returns per-sample MSE reconstruction error."""
            x_hat = self.forward(x)
            return torch.mean((x - x_hat) ** 2, dim=(1, 2))

else:
    # Dummy stubs so AnomalyDetector can still reference these names safely
    LSTMEncoder = None
    LSTMDecoder = None
    LSTMAutoencoder = None


# ── Feature Extraction ─────────────────────────────────────────────────────────

def extract_features(state: dict) -> np.ndarray:
    """
    Extract a flat feature vector from a SimulationEngine state snapshot.
    All features are normalized to approximately [0, 1] range.
    Returns: np.ndarray of shape (N_FEATURES,)
    """
    bus = state.get("bus_bar", {})
    gens = state.get("generators", [])

    g1 = next((g for g in gens if g["id"] == "GEN_01"), {})
    g2 = next((g for g in gens if g["id"] == "GEN_02"), {})

    # Max rated current for a 1500kW, 440V, 3-phase generator:
    # I_rated = P / (sqrt(3) * V * PF) = 1500000 / (1.732 * 440 * 0.85) ≈ 2316 A
    # We use 3000A as a safe upper bound (covers fault currents up to 2x rated)
    MAX_CURRENT_A = 3000.0

    g1_current = np.clip(g1.get("current_a", 0.0), 0.0, MAX_CURRENT_A)
    g2_current = np.clip(g2.get("current_a", 0.0), 0.0, MAX_CURRENT_A)

    return np.array([
        bus.get("voltage_v", 440.0) / 440.0,
        bus.get("frequency_hz", 60.0) / 60.0,
        g1.get("load_percent", 0.0) / 100.0,
        g2.get("load_percent", 0.0) / 100.0,
        g1.get("temperature_c", 80.0) / 150.0,
        g2.get("temperature_c", 80.0) / 150.0,
        g1_current / MAX_CURRENT_A,
        g2_current / MAX_CURRENT_A,
        bus.get("total_load_kw", 0.0) / 4000.0,
        np.clip(bus.get("power_imbalance_kw", 0.0) / 500.0, -1, 1),
    ], dtype=np.float32)


# ── Anomaly Detector ───────────────────────────────────────────────────────────

class AnomalyDetector:
    """
    Wraps the LSTM Autoencoder for real-time anomaly detection.
    Falls back to z-score based statistical detection if PyTorch is unavailable.
    Maintains a sliding window of feature vectors and predicts on each update.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        threshold: float = 0.025,
        seq_len: int = SEQUENCE_LEN,
    ):
        self.threshold = threshold
        self.seq_len = seq_len
        self._window: List[np.ndarray] = []
        self._last_score: float = 0.0
        self._is_anomaly: bool = False
        self._use_torch = TORCH_AVAILABLE
        # Warmup: suppress AI scoring for the first N steps after startup.
        # The sim is pre-warmed at init so temperatures are already stable.
        # We only need to fill the LSTM window (30 steps) + a small buffer = 40 steps (20s).
        self._warmup_steps_total = 40
        self._warmup_steps_done = 0

        if self._use_torch:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model = LSTMAutoencoder(seq_len=seq_len).to(self.device)
            if model_path:
                self.load(model_path)
        else:
            # Statistical baseline for z-score detection
            self._baseline_mean: Optional[np.ndarray] = None
            self._baseline_std: Optional[np.ndarray] = None
            self._warmup_buffer: List[np.ndarray] = []
            self._warmup_done = False

    def load(self, path: str):
        """Load a pre-trained model checkpoint (torch only)."""
        if not TORCH_AVAILABLE:
            return
            
        # Allow numpy scalar for torch 2.6+ weights_only loading
        import numpy as np
        try:
            torch.serialization.add_safe_globals([np._core.multiarray.scalar])
        except AttributeError:
            pass # Older torch versions don't have this or don't need it
            
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(checkpoint["model_state"])
        self.threshold = checkpoint.get("threshold", self.threshold)
        self.model.eval()

    def save(self, path: str):
        """Save model checkpoint (torch only)."""
        if not TORCH_AVAILABLE:
            return
        torch.save({
            "model_state": self.model.state_dict(),
            "threshold": self.threshold,
        }, path)

    def _statistical_score(self, features: np.ndarray) -> float:
        """
        Simple z-score based anomaly score as fallback.
        Returns MSE-like score based on how far values deviate from baseline.
        """
        if not self._warmup_done:
            self._warmup_buffer.append(features)
            if len(self._warmup_buffer) >= 60:
                buf = np.stack(self._warmup_buffer)
                self._baseline_mean = buf.mean(axis=0)
                self._baseline_std = np.clip(buf.std(axis=0), 1e-6, None)
                self._warmup_done = True
            return 0.0

        z = (features - self._baseline_mean) / self._baseline_std
        score = float(np.mean(z ** 2))
        # Normalize to roughly match the LSTM score range (0-0.1 normal)
        return score * 0.001

    def update(self, state: dict) -> dict:
        """
        Ingest a new grid state snapshot and return the anomaly assessment.
        """
        features = extract_features(state)
        self._window.append(features)
        if len(self._window) > self.seq_len:
            self._window.pop(0)

        if self._use_torch:
            # Suppress inference during warmup (generators starting cold)
            if self._warmup_steps_done < self._warmup_steps_total:
                self._warmup_steps_done += 1
                return {"score": 0.0, "anomaly": False, "confidence": 0.0,
                        "threshold": self.threshold, "mode": "lstm",
                        "warmup": True, "warmup_progress": round(self._warmup_steps_done / self._warmup_steps_total, 2)}

            if len(self._window) < self.seq_len:
                return {"score": 0.0, "anomaly": False, "confidence": 0.0,
                        "threshold": self.threshold, "mode": "lstm"}

            x = np.stack(self._window, axis=0)
            x_t = torch.tensor(x, dtype=torch.float32).unsqueeze(0).to(self.device)

            with torch.no_grad():
                err = self.model.reconstruction_error(x_t)

            self._last_score = float(err.item())
        else:
            self._last_score = self._statistical_score(features)

        self._is_anomaly = self._last_score > self.threshold
        confidence = min(self._last_score / (self.threshold * 3), 1.0) if self._is_anomaly else 0.0

        return {
            "score": round(self._last_score, 6),
            "anomaly": self._is_anomaly,
            "confidence": round(confidence, 4),
            "threshold": self.threshold,
            "mode": "lstm" if self._use_torch else "statistical",
        }

    def get_last_result(self) -> dict:
        return {
            "score": round(self._last_score, 6),
            "anomaly": self._is_anomaly,
            "threshold": self.threshold,
            "mode": "lstm" if self._use_torch else "statistical",
        }

