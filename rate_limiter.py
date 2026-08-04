import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, max_requests=5, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.users = defaultdict(list)
    
    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        self.users[user_id] = [ts for ts in self.users[user_id] if ts > now - self.time_window]
        if len(self.users[user_id]) >= self.max_requests:
            return False
        self.users[user_id].append(now)
        return True
    
    def get_wait_time(self, user_id: int) -> int:
        now = time.time()
        self.users[user_id] = [ts for ts in self.users[user_id] if ts > now - self.time_window]
        if len(self.users[user_id]) < self.max_requests:
            return 0
        oldest = min(self.users[user_id])
        return int(self.time_window - (now - oldest)) + 1

rate_limiter = RateLimiter(max_requests=5, time_window=60)