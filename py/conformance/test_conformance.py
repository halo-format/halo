"""Conformance harness (Python).

Loads the shared vectors from ../../conformance/vectors and asserts the halo_format core matches
them: canonical bytes, handles, node handles, and envelopes (excluding the non-hashed source
field). These are the same vectors the TypeScript harness runs, which is what guarantees a halo
produced in one port verifies and navigates in the other.

TODO: implement once canonical + hash land. See conformance/README.md.
"""
