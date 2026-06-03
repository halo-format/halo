"""The Store protocol plus MemoryStore and FileStore.

    put(bytes) -> Handle   (content-addressed, idempotent, stores once)
    get(handle) -> bytes   (raises UnknownHandle if absent)
    has(handle) -> bool
    get_many(handles) -> list[bytes | None]   (optional multi-get)

Untrusted by design: every read verifies, so a buggy/hostile store cannot substitute data
undetected. MemoryStore = in-process dict; FileStore = one file per handle under a dir.

Note on async: the TypeScript Store is async (Promise-returning) per the SDK contract. The Python
port is synchronous, which is idiomatic for the in-process and filesystem stores; a heavy/remote
Python adapter can expose an async variant. The navigator built on top stays sync to match.
"""

import os

from .errors import StoreError, UnknownHandle
from .hash import hash_bytes


def _hex_of(handle: str) -> str:
    """A handle is "h:" + hex; the hex alone is the on-disk filename for FileStore."""
    return handle[2:] if handle.startswith("h:") else handle


class MemoryStore:
    """In-process content-addressed store — the light deployment and the default for tests."""

    def __init__(self, alg: str = "sha256"):
        self._map: dict[str, bytes] = {}
        self._alg = alg

    def put(self, data: bytes) -> str:
        handle = hash_bytes(data, self._alg)
        # Idempotent + immutable: first writer wins, identical content is a no-op.
        self._map.setdefault(handle, data)
        return handle

    def get(self, handle: str) -> bytes:
        try:
            return self._map[handle]
        except KeyError:
            raise UnknownHandle(handle) from None

    def has(self, handle: str) -> bool:
        return handle in self._map

    def get_many(self, handles: list[str]) -> list[bytes | None]:
        return [self._map.get(h) for h in handles]

    def __len__(self) -> int:
        return len(self._map)


class FileStore:
    """One file per handle under a directory — cross-step persistence inside a sandbox."""

    def __init__(self, directory: str, alg: str = "sha256"):
        self._dir = directory
        self._alg = alg
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise StoreError(f"could not create store dir {directory}: {e}") from e

    def _path_for(self, handle: str) -> str:
        return os.path.join(self._dir, _hex_of(handle))

    def put(self, data: bytes) -> str:
        handle = hash_bytes(data, self._alg)
        path = self._path_for(handle)
        if not os.path.exists(path):  # immutable: never overwrite
            with open(path, "wb") as f:
                f.write(data)
        return handle

    def get(self, handle: str) -> bytes:
        try:
            with open(self._path_for(handle), "rb") as f:
                return f.read()
        except FileNotFoundError:
            raise UnknownHandle(handle) from None
        except OSError as e:
            raise StoreError(f"could not read {handle}: {e}") from e

    def has(self, handle: str) -> bool:
        return os.path.exists(self._path_for(handle))

    def get_many(self, handles: list[str]) -> list[bytes | None]:
        out: list[bytes | None] = []
        for h in handles:
            try:
                out.append(self.get(h))
            except UnknownHandle:
                out.append(None)
        return out
