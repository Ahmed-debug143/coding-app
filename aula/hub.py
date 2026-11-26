import asyncio
import threading


class Hub:
    """Diffuse les événements temps réel aux sessions ouvertes sur ce processus."""

    def __init__(self):
        self.loop = None
        self.clients: dict[int, set] = {}
        self.online: set[int] = set()
        self._lock = threading.Lock()

    def bind(self, loop):
        self.loop = loop

    async def register(self, user_id: int):
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self.clients.setdefault(user_id, set()).add(queue)
            self.online.add(user_id)
        return queue

    def unregister(self, user_id: int, queue):
        with self._lock:
            queues = self.clients.get(user_id, set())
            queues.discard(queue)
            if not queues:
                self.clients.pop(user_id, None)
                self.online.discard(user_id)

    def snapshot(self) -> list[int]:
        with self._lock:
            return list(self.online)

    def publish(self, user_ids, event: dict):
        loop = self.loop
        if loop is None:
            return
        ids = [int(item) for item in dict.fromkeys(user_ids)]
        if event.get("type") == "force_disconnect" and not event.get("group_id"):
            with self._lock:
                for user_id in ids:
                    queues = self.clients.get(user_id)
                    if queues:
                        for queue in list(queues):
                            while not queue.empty():
                                try:
                                    queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    break
        asyncio.run_coroutine_threadsafe(self._fanout(ids, event), loop)

    async def _fanout(self, user_ids: list[int], event: dict):
        with self._lock:
            queues = []
            for user_id in user_ids:
                queues.extend(list(self.clients.get(user_id, ())))
        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(event)


hub = Hub()
