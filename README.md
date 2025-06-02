# Real-time statistics
This project provides a FastAPI service (price_stats.py) that ingests tick data and exposes real-time statistics over a 60-second sliding window, plus a tick simulation client (tick_simulation.py) that generates random ticks and queries the service. Below are instructions for running, design assumptions, and potential improvements.



## Overview
#### `price_stats.py` implements a REST API with three endpoints:

- `POST /ticks` – ingest a tick: `{ "instrument": "...", "price": ..., "timestamp": ... }`

- `GET /statistics` – return global statistics (avg, min, max, count) over all instruments for the last 60 seconds

- `GET /statistics/{instrument}` – return statistics for a single instrument over the last 60 seconds

Internally, it uses a fixed-size sliding window of 60 “buckets” (one per second) both globally and per instrument, ensuring O(1) time and memory for each GET. A single `threading.Lock` makes it safe for concurrent POSTs/GETs. Out-of-order ticks (timestamps in the past/future) are slotted correctly if within the 60-second window; anything older than 60 seconds is rejected with HTTP 204.

#### `tick_simulation.py` is an example client that:

- Spawns multiple threads to randomly POST tick data to `/ticks` at radomised intervals.

- Periodically (every 2 seconds) fetches and prints global statistics (GET /statistics) and per-instrument statistics (GET /statistics/{instrument}).

- Demonstrates both idle periods where trades are stale and when many tick are processed in parrallel to exercise concurrency and sliding-window removal in real time.

## Requirements
Python 3.8+

Dependencies are found in `requirements.txt`.

## How to Run the Project
- Start the FastAPI Service (price_stats.py)

`python -m uvicorn price_stats:app --reload`
This will launch the FastAPI server at `http://127.0.0.1:8000`.

Swagger UI is available at `http://127.0.0.1:8000/docs`. `TODO` I'll like to spend more time on this part.
Swagger currently shows
Verify manually (optional):

`GET http://127.0.0.1:8000/statistics` should return:
	
Response body
`{
  "avg": 0,
  "max": 0,
  "min": 0,
  "count": 0
}`
-  Run the Tick Simulation Client (tick_simulation.py)
Ensure the FastAPI service is running (previous step).

Run the client:

`python tick_simulation.py`. 
The output on the console for each posted tick (e.g. `[Thread 1] Posted tick: AAPL @ 123.45`) and, every 2 seconds, 
polled global stats and two random instruments’ stats.

Press `Ctrl+C` to stop.

## Assumptions
Below are the design assumptions made while developing both `price_stats.py` and `tick_simulation.py`.

**Service‐Side Assumptions (price_stats.py)**
- No Standard Aggregation Libraries

- We do not use any third-party or standard-statistics libraries (e.g., statistics.mean, pandas, etc.). All aggregation (sum, count, min, max) is implemented manually in our custom buckets.

- In-Memory Only

- All data structures (sliding window, per‐instrument maps) live in memory.

- No external database or persistent storage is used. If the service restarts, all data is lost.

**Code Quality**

- We follow idiomatic Python: clear variable names, type annotations, docstrings for every class and method.

- We use Pydantic to validate incoming JSON and enforce correct types.

## Test Coverage

- A full `test_price_stats.py` testing framework using `pytest` and FastAPI’s `TestClient`.

- Empty‐state behavior where we have no ticks yet.

-  Insertion and  global/instrument statistics.

- Rejecting old‐timestamp ticks which are more than  60 seconds.

- Acceptance of future ticks, if the tick occur within 60 seconds of this time period.

- Concurrent POSTs to the same instrument to ensure thread safety and correct aggregation

**O(1) GET Performance**
- Both GET /statistics and GET /statistics/{instrument} run in constant time and memory.
- Global aggregates (`self.global_sum`, `self.global_count`, `self.global_min`, `self.global_max`) are maintained incrementally.


**Concurrency Safety**
- We use a single `threading.Lock` to guard:
  - `add_tick(...)` for both global and  per‐instrument bucket updates.
- No two threads can modify shared state simultaneously.

**Time Discrepancies**
- Each incoming tick carries its own timestamp (in milliseconds).
- This is computed by ts_sec = timestamp_ms // 1000 to determine which bucket (0–59) it belongs to.
- If timestamp_ms is older than (now_ms − 60 000), we reject with HTTP 204 NO_CONTENT, geiven it’s outside our 60-second window.


## Simulation‐Side Assumptions (`tick_simulation.py`)
- We have a random Instrument set with pseudo prices for the  five instruments: ["AAPL", "GOOG", "MSFT", "TSLA", "AMZN"].
- We model unpredictable traffic where the posting thread sleeps a random interval up to 0.2 s between POSTs.
- We demonstrate idle periods.
- 

# What to Improve If I Had More Time?
- Consider adding rate limits if we decide to set a boundary to the max number of ticks we should allow to get retrieved.
- Sharding Locking to reduce a potential bottleneck because the single lock serialises all `add_ticks()`, therefore there should be a lock specific to each instrument.
- Work on in-memory storage, thus in the event that the process restarts, we can reload the last 60 seconds.
- Included versioning for API for clear documentation, currently we do have swaggerUI but this needs to have a versioning scheme.
