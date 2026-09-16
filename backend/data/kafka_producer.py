"""
Kafka Producer - Streams synthetic grid snapshots to a Kafka topic.
Simulates real-time telemetry ingestion from shipboard SCADA sensors.
"""

import json
import time
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.synthetic_generator import SyntheticDataGenerator, snapshot_to_dict

try:
    from kafka import KafkaProducer
    from kafka.errors import NoBrokersAvailable
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_GRID_TELEMETRY = "ship.grid.telemetry"
TOPIC_FAULTS = "ship.grid.faults"


def create_producer(retries: int = 5) -> "KafkaProducer":
    """Create Kafka producer with retry logic."""
    for attempt in range(retries):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
            )
            logger.info(f"✅ Connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
            return producer
        except NoBrokersAvailable:
            logger.warning(f"Kafka not ready, retrying ({attempt + 1}/{retries})...")
            time.sleep(5)
    raise RuntimeError("Could not connect to Kafka after multiple attempts.")


def run_producer(duration_seconds: int = 3600, interval_ms: int = 1000):
    """
    Continuously streams synthetic ship grid data to Kafka.
    Runs for `duration_seconds` (default: 1 hour).
    """
    if not KAFKA_AVAILABLE:
        logger.warning("kafka-python not installed. Running in LOCAL STDOUT mode.")
        _run_local_mode(duration_seconds, interval_ms)
        return

    producer = create_producer()
    gen = SyntheticDataGenerator()

    logger.info(f"🚢 Starting data stream for {duration_seconds}s → Kafka topic: '{TOPIC_GRID_TELEMETRY}'")

    for snap in gen.generate_stream(duration_seconds=duration_seconds, fault_probability=0.08):
        data = snapshot_to_dict(snap)

        # Send all telemetry to main topic
        producer.send(TOPIC_GRID_TELEMETRY, value=data)

        # If fault, also publish to dedicated faults topic
        if snap.scenario != "normal":
            fault_event = {
                "timestamp": snap.timestamp,
                "fault_type": snap.scenario,
                "fault_component": snap.fault_component,
                "anomaly_score": snap.anomaly_score,
            }
            producer.send(TOPIC_FAULTS, value=fault_event)
            logger.warning(f"⚡ FAULT INJECTED: {snap.scenario} | Component: {snap.fault_component} | Score: {snap.anomaly_score:.3f}")

        producer.flush()
        time.sleep(interval_ms / 1000)

    producer.close()
    logger.info("Producer finished.")


def _run_local_mode(duration_seconds: int, interval_ms: int):
    """Fallback: print data to stdout when Kafka is unavailable."""
    gen = SyntheticDataGenerator()
    for snap in gen.generate_stream(duration_seconds=duration_seconds, fault_probability=0.08):
        data = snapshot_to_dict(snap)
        print(json.dumps(data))
        time.sleep(interval_ms / 1000)


if __name__ == "__main__":
    run_producer(duration_seconds=600, interval_ms=500)
