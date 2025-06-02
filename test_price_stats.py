# test_price_stats.py
import time
from fastapi.testclient import TestClient
import pytest

from price_stats import app

client = TestClient(app)


def now_ms():
    return int(time.time() * 1000)


def test_post_and_get_all_and_instrument_empty():
    # No ticks yet
    r = client.get("/statistics")
    assert r.status_code == 200
    assert r.json() == {"avg": 0.0, "max": 0.0, "min": 0.0, "count": 0}

    r = client.get("/statistics/FOO")
    assert r.status_code == 200
    assert r.json() == {"avg": 0.0, "max": 0.0, "min": 0.0, "count": 0}


def test_post_tick_and_stats():
    ts = now_ms()
    # Post three ticks
    client.post("/ticks", json={"instrument": "A", "price": 10.0, "timestamp": ts})
    client.post("/ticks", json={"instrument": "A", "price": 20.0, "timestamp": ts})
    client.post("/ticks", json={"instrument": "B", "price": 30.0, "timestamp": ts})

    # Global
    r = client.get("/statistics")
    stats = r.json()
    assert stats["count"] == 3
    assert stats["min"] == 10.0
    assert stats["max"] == 30.0
    assert abs(stats["avg"] - 20.0) < 1e-6

    # Instrument A
    r = client.get("/statistics/A")
    stats = r.json()
    assert stats["count"] == 2
    assert stats["min"] == 10.0
    assert stats["max"] == 20.0
    assert abs(stats["avg"] - 15.0) < 1e-6

    # Instrument B
    r = client.get("/statistics/B")
    stats = r.json()
    assert stats["count"] == 1
    assert stats["min"] == stats["max"] == stats["avg"] == 30.0


def test_old_tick_rejected():
    old_ts = now_ms() - 61_000
    r = client.post("/ticks", json={"instrument": "A", "price": 100.0, "timestamp": old_ts})
    assert r.status_code == 204

def test_out_of_order_tick_within_window():
    ts = now_ms()
    # future tick within a few ms ahead is accepted if within window
    future_ts = ts + 500
    r = client.post("/ticks", json={"instrument": "C", "price": 5.0, "timestamp": future_ts})
    assert r.status_code == 201
    # Stats should include it
    r2 = client.get("/statistics/C")
    assert r2.json()["count"] >= 1


def test_concurrent_posts_and_gets():
    import threading

    ts = now_ms()
    def post_many():
        for i in range(100):
            client.post("/ticks", json={"instrument": "X", "price": float(i), "timestamp": ts})

    threads = [threading.Thread(target=post_many) for _ in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()

    r = client.get("/statistics/X")
    stats = r.json()
    # 5 * 100 = 500 ticks
    assert stats["count"] == 500
    assert stats["min"] == 0.0
    assert stats["max"] == 99.0
    assert abs(stats["avg"] - (sum(range(100)) / 100)) < 1e-6
