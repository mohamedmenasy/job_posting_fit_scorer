"""robots.txt lookups, cached per host (import §6). A missing or unreadable file means allowed."""

import time
from urllib.robotparser import RobotFileParser

TTL_SECONDS = 3600
MAX_HOSTS = 200


class RobotsCache:
    def __init__(self, ttl: float = TTL_SECONDS, max_hosts: int = MAX_HOSTS):
        self._ttl = ttl
        self._max_hosts = max_hosts
        self._entries: dict[str, tuple[float, RobotFileParser | None]] = {}

    def get(self, origin: str) -> RobotFileParser | None | str:
        entry = self._entries.get(origin)
        if entry is None or time.monotonic() - entry[0] > self._ttl:
            return "miss"
        return entry[1]

    def put(self, origin: str, parser: RobotFileParser | None) -> None:
        if len(self._entries) >= self._max_hosts:
            self._entries.pop(next(iter(self._entries)))
        self._entries[origin] = (time.monotonic(), parser)

    @staticmethod
    def parse(text: str) -> RobotFileParser:
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        return parser
