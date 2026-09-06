"""
Minimal stand-in for Klipper's reactor, driven by a manual clock.

Supports the subset the ACE plugin uses: ``monotonic``, ``register_timer``,
``unregister_timer``, ``update_timer``, ``pause``, ``NOW`` and ``NEVER``.
Timers fire only when the test advances the clock with ``advance`` or
``run_until``, so tests are deterministic and never sleep.
"""


class _Timer:
    def __init__(self, callback, waketime):
        self.callback = callback
        self.waketime = waketime


class FakeReactor:
    NOW = 0.0
    NEVER = 9999999999999999.0

    def __init__(self, start_time=1000.0):
        self._now = start_time
        self._timers = []
        self.fired = []  # (time, timer) history for assertions

    # --- Klipper reactor API -------------------------------------------------
    def monotonic(self):
        return self._now

    def register_timer(self, callback, waketime=NEVER):
        timer = _Timer(callback, waketime)
        self._timers.append(timer)
        return timer

    def unregister_timer(self, timer):
        timer.waketime = self.NEVER
        if timer in self._timers:
            self._timers.remove(timer)

    def update_timer(self, timer, waketime):
        timer.waketime = waketime

    def pause(self, waketime):
        """Block until ``waketime`` while running due timers (what Klipper does)."""
        self.run_until(waketime)

    # --- test helpers --------------------------------------------------------
    def advance(self, seconds):
        self.run_until(self._now + seconds)

    def run_until(self, end_time, max_iterations=10000):
        """Advance the clock to ``end_time``, firing every timer that comes due."""
        for _ in range(max_iterations):
            due = [t for t in self._timers if t.waketime <= end_time]
            if not due:
                break
            timer = min(due, key=lambda t: t.waketime)
            self._now = max(self._now, timer.waketime)
            timer.waketime = self.NEVER
            next_wake = timer.callback(self._now)
            self.fired.append((self._now, timer))
            if next_wake is None or next_wake == self.NEVER:
                if timer in self._timers:
                    self._timers.remove(timer)
            else:
                timer.waketime = next_wake
        else:
            raise RuntimeError("FakeReactor: timer storm, a timer keeps returning NOW")
        self._now = max(self._now, end_time)

    @property
    def pending_timers(self):
        return [t for t in self._timers if t.waketime != self.NEVER]
