"""The Store protocol plus MemoryStore and FileStore.

    put(bytes) -> Handle   (content-addressed, idempotent, stores once)
    get(handle) -> bytes   (raises UnknownHandle if absent)
    has(handle) -> bool
    get_many(handles) -> list[bytes | None]   (optional multi-get)

Untrusted by design: every read verifies, so a buggy/hostile store cannot substitute data
undetected. MemoryStore = in-process dict; FileStore = one file per handle under a dir.
"""
