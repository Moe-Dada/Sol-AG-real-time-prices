"""
tick_simulation.py

This is an example script assumes your FastAPI service (price_stats.py) is running locally at http://127.0.0.1:8000.

For testing purposes:
1. Spawn multiple threads that occasionally POST random tick data to `/ticks`.
2. Periodically GET `/statistics` (global) and `/statistics/{instrument}` for a few instruments.
3. Demonstrate idle times (no posts) and bursts (many threads posting in parallel).
4. Print out the responses so you can see how the sliding‐window statistics update in real time.
"""

import threading
import time
import random
import requests

BASE_URL = "http://127.0.0.1:8000"

INSTRUMENTS = ["AAPL", "GOOG", "MSFT", "TSLA", "AMZN"]


def post_ticks_forever(thread_id: int):
    """
    Thread that continuously and randomly sends ticks for a random instrument.
    """
    while True:
        # Pick a random instrument and a random price
        instr = random.choice(INSTRUMENTS)
        price = round(random.uniform(50.0, 500.0), 2)
        timestamp_ms = int(time.time() * 1000)

        payload = {
            "instrument": instr,
            "price": price,
            "timestamp": timestamp_ms,
        }

        try:
            r = requests.post(f"{BASE_URL}/ticks", json=payload, timeout=1.0)
            if r.status_code == 201:
                print(f"[Thread {thread_id}] Posted tick: {instr} @ {price:.2f}")
            elif r.status_code == 204:
                # tick was older than 60s; skip
                print(f"[Thread {thread_id}] Old tick (ignored).")
            else:
                # could be a 422 or something else
                print(f"[Thread {thread_id}] Unexpected status {r.status_code}")
        except requests.RequestException as e:
            print(f"[Thread {thread_id}] Error posting tick: {e}")

        # Sleep for up to 200ms before sending the next tick
        time.sleep(random.uniform(0.0, 0.2))


def poll_statistics_forever():
    """
    Periodically (every 2 seconds) fetch and print global stats and per-instrument stats.
    """
    while True:
        try:
            # 1) Global stats
            r_global = requests.get(f"{BASE_URL}/statistics", timeout=1.0)
            if r_global.status_code == 200:
                data = r_global.json()
                print(
                    f"→ [Global Stats] count={data['count']}  "
                    f"avg={data['avg']:.2f}  min={data['min']:.2f}  max={data['max']:.2f}"
                )
            else:
                print(f"→ [Global Stats] Unexpected status {r_global.status_code}")
        except requests.RequestException as e:
            print(f"→ [Global Stats] Request error: {e}")

        # 2) Per-instrument stats (pick a couple at random each time)
        for instr in random.sample(INSTRUMENTS, k=2):
            try:
                r_inst = requests.get(f"{BASE_URL}/statistics/{instr}", timeout=1.0)
                if r_inst.status_code == 200:
                    d = r_inst.json()
                    print(
                        f"   [Stats {instr}] count={d['count']}  "
                        f"avg={d['avg']:.2f}  min={d['min']:.2f}  max={d['max']:.2f}"
                    )
                else:
                    print(f"   [Stats {instr}] Unexpected status {r_inst.status_code}")
            except requests.RequestException as e:
                print(f"   [Stats {instr}] Request error: {e}")

        # Wait 2 seconds before polling again
        time.sleep(2.0)


def main():
    # 1) Start a few threads that post ticks
    num_poster_threads = 5
    for i in range(num_poster_threads):
        t = threading.Thread(target=post_ticks_forever, args=(i + 1,), daemon=True)
        t.start()

    # 2) Start one thread that polls statistics
    poller = threading.Thread(target=poll_statistics_forever, daemon=True)
    poller.start()

    # 3) Let the script run indefinitely (Ctrl+C to stop)
    print(
        "Example client started.\n"
        f"- {num_poster_threads} posting threads sending random ticks.\n"
        "- 1 polling thread fetching global + instrument stats every 2s.\n"
        "Press Ctrl+C to quit.\n"
    )

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nShutting down example client.")


if __name__ == "__main__":
    main()
