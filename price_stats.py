# price_stats.py
import threading
import time
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

SLIDING_WINDOW = 60  # sliding time interval

class Tick(BaseModel):
    """ Data models using Pydantic’s BaseModel to handle input validation.
    and type coercion when used as request or response bodies in FastAPI.

    :param instrument (str): String identifier for the financial instrument (e.g., "AAPL".).
    :param price (float): Trade price for that instrument at this tick.
    :param timestamp  (int): timestamp in milliseconds .
    """
    instrument: str
    price: float
    timestamp: int

class Statistics(BaseModel):
    """
    This class defines the shape of the response payload for the statistics endpoints.
    When a FastAPI route returns an instance of Statistics, FastAPI automatically serializes
    it into a JSON representation.

    :param avg (float): The average price across all ticks.
    :param max (float): The maximum price seen in the last 60 seconds.
    :param min (float): The minimum price seen in the last 60 seconds.
    :param count (int): The total number of ticks that fell into the last 60-second window.
    """
    avg: float
    max: float
    min: float
    count: int

class _Bucket:
    """
    This class is a  container that holds aggregated tick statistics for exactly one second,
    where __slots__ defines which attributes that are allowed for each _Bucket.

    :param timestamp (int): records a tick into a bucket so we compute ts_sec = timestamp_ms // 1000.
    If later a new tick maps to the same bucket index but a different ts_sec, we know this bucket is “stale”
    and must be reset.
    :param sum (float): Accumulates the total of all prices for ticks whose UNIX‐second equals timestamp.
    :param count (int): How many ticks have been added to this bucket during its current second.
    :param min_price (float): Tracks the minimum tick price seen within that second.
    :param max_price (float): Tracks the maximum tick price seen within that second.
    """
    __slots__ = ("timestamp", "sum", "count", "min_price", "max_price")

    def __init__(self):
        self.timestamp: int = 0
        self.sum: float = 0.0
        self.count: int = 0
        self.min_price: float = float("inf")
        self.max_price: float = float("-inf")

    def reset(self, new_timestamp: int):
        self.timestamp = new_timestamp
        self.sum = 0.0
        self.count = 0
        self.min_price = float("inf")
        self.max_price = float("-inf")

class InstrumentStats:
    """
    The InstrumentStats class maintains a per‐instrument, 60‐second sliding‐window of tick data
    attributes using the same circular‐buffer approach as the global aggregator.
    :param buckets (list): A list of exactly SLIDING_WINDOW (60 sec) _Bucket objects. Where each _Bucket
    holds aggregated data (sum, count, min_price, max_price) for ticks that share the same UNIX‐second timestamp.
    :param sum (float): the total of all tick prices for this instrument over the last 60 seconds.
    :param count (int): how many ticks have been recorded for this instrument in that same window.
    :param min_price (float): the smallest tick price seen for this instrument in the last 60 seconds.
    :param max_price (float): the largest tick price seen for this instrument in the last 60 seconds.
    """
    def __init__(self):
        self.buckets = [ _Bucket() for _ in range(SLIDING_WINDOW) ]
        self.sum: float = 0.0
        self.count: int = 0
        self.min_price: float = float("inf")
        self.max_price: float = float("-inf")

    def add_tick(self, price: float, ts_sec: int):
        idx = ts_sec % SLIDING_WINDOW
        bucket = self.buckets[idx]

        # If bucket is stale we remove old data
        if bucket.timestamp != ts_sec:
            if bucket.count > 0:
                self.sum   -= bucket.sum
                self.count -= bucket.count
            bucket.reset(ts_sec)

        # add new tick to respective bucket
        bucket.sum += price
        bucket.count += 1

        #update min and max prices
        bucket.min_price = min(bucket.min_price, price)
        bucket.max_price = max(bucket.max_price, price)

        # update rolling totals
        self.sum += price
        self.count += 1
        self.min_price = min(self.min_price, price)
        self.max_price = max(self.max_price, price)

    def capture(self) -> Statistics:
        """
        If no ticks have been recorded in the last 60 seconds,
        we return a Statistics where all fields are zero.
        """
        if self.count == 0:
            return Statistics(avg=0.0, max=0.0, min=0.0, count=0)

        # else we return computed statistics
        return Statistics(
            avg=self.sum / self.count,
            max=self.max_price,
            min=self.min_price,
            count=self.count,
        )

class StatisticsComputation:
    """
    Maintains a 60-second sliding window of tick data for O(1) retrieval of avg, min, max, and count.
    :param global_buckets (list): We create global_buckets to capture a list of buckets for each second within 60 seconds.
    :param global_sum (float): We compute running sum of all prices in the last 60 seconds (across every instrument).
    :param global_count (int): We compute total number of ticks in the last 60 seconds.
    :param global_min (float): We track the minimum price seen in that same window.
    :param global_max (float): We track the maximum price seen in that same window.
    :param instruments (dict): We define a dictionary that maps each instrument ID (a string type) to its own InstrumentStats
    object, where each InstrumentStats internally maintains its own per-instrument aggregates (sum, count, min, max).
    :param lock Lock: To ensure that we never corrupt the sliding 60-second computation when multiple threads
    call add_tick or the GET methods concurrently.
    """
    def __init__(self):
        self.global_buckets = [ _Bucket() for _ in range(SLIDING_WINDOW) ]
        self.global_sum: float = 0.0
        self.global_count: int = 0
        self.global_min: float = float("inf")
        self.global_max: float = float("-inf")
        self.instruments: Dict[str, InstrumentStats] = {}
        self.lock = threading.Lock()

    def add_tick(self, instrument: str, price: float, timestamp_ms: int) -> bool:
        """
        This method is responsible for adding a new tick price at a given timestamp
         into both the global sliding‐window and respecitve per‐instrument sliding‐window.
        """
        now_ms = int(time.time() * 1000)
        if timestamp_ms < now_ms - SLIDING_WINDOW * 1000:
            return False  # too old

        ts_sec = timestamp_ms // 1000
        idx = ts_sec % SLIDING_WINDOW

        with self.lock:
            # update global bucket
            bucket = self.global_buckets[idx]
            if bucket.timestamp != ts_sec:
                if bucket.count > 0:
                    # evict old
                    self.global_sum   -= bucket.sum
                    self.global_count -= bucket.count
                bucket.reset(ts_sec)

            # add to global
            bucket.sum += price
            bucket.count += 1
            bucket.min_price = min(bucket.min_price, price)
            bucket.max_price = max(bucket.max_price, price)

            # update global aggregates
            self.global_sum += price
            self.global_count += 1
            self.global_min = min(self.global_min, price)
            self.global_max = max(self.global_max, price)

            # update per-instrument
            inst = self.instruments.get(instrument)
            if inst is None:
                inst = InstrumentStats()
                self.instruments[instrument] = inst
            inst.add_tick(price, ts_sec)

        return True

    def get_statistics_all(self) -> Statistics:
        """
        To retrieve statistics we use the context manager self.lock to make sure no concurrent thread is mutating
        the global aggregates while we read them. If global_count == 0, there are no ticks in the last 60 seconds,
        and we reset the statistics.
        """
        with self.lock:
            if self.global_count == 0:
                return Statistics(avg=0.0, max=0.0, min=0.0, count=0)
            return Statistics(
                avg=self.global_sum / self.global_count,
                max=self.global_max,
                min=self.global_min,
                count=self.global_count,
            )

    def get_statistics_instrument(self, instrument: str) -> Statistics:
        """
        We retrieve statistics again, we use the context manager self.lock to ensure thread safety.
        We look up inst = self.instruments.get(instrument). If there’s no entry for that instrument
        all of its buckets have been evicted in the last 60 seconds), we return zeros.
        """
        with self.lock:
            inst = self.instruments.get(instrument)
            if inst is None or inst.count == 0:
                return Statistics(avg=0.0, max=0.0, min=0.0, count=0)
            return inst.capture()

app = FastAPI()
service = StatisticsComputation()

# POST /ticks
# we return 201 for success we
@app.post("/ticks", status_code=status.HTTP_201_CREATED)
def post_tick(tick: Tick):
    ok = service.add_tick(tick.instrument, tick.price, tick.timestamp)
    if not ok:
        # older than 60s, thus we return 204 No Content
        raise HTTPException(status_code=status.HTTP_204_NO_CONTENT)
    return {}

# GET /statistics
@app.get("/statistics", response_model=Statistics)
def get_stats():
    return service.get_statistics_all()

# GET /statistics/{instrument_identifier}
@app.get("/statistics/{instrument}", response_model=Statistics)
def get_stats_instrument(instrument: str):
    return service.get_statistics_instrument(instrument)