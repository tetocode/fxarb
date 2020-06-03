from typing import Dict


def new_account(service: str, *,
                balance: float = 0,
                equity: float = 0,
                pl: float = 0,
                margin: float = 0,
                available_margin: float = 0,
                margin_ratio: float = 0,
                positions: Dict[str, int] = None):
    d = locals().copy()
    d.update(positions=positions or {})
    return d


def with_lock(*, blocking=True, timeout=None, default_return=lambda: None):
    def decorator(f):
        def wrapper(self, *args, **kwargs):
            if self._lock.acquire(blocking=blocking, timeout=timeout):
                try:
                    return f(self, *args, **kwargs)
                finally:
                    self._lock.release()
            else:
                return default_return()

        return wrapper

    return decorator
