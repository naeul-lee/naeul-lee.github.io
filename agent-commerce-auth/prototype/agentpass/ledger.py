"""Append-only hash-chained audit ledger with signed checkpoints (ADR-0007)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .crypto import KeyPair, VerificationError, b64u, canonical_json, jws_sign, jws_verify, sha256_b64u

GENESIS = "0" * 43
CHECKPOINT_TYP = "agentpass-checkpoint+jwt"


@dataclass
class Entry:
    seq: int
    prev_hash: str
    event_type: str
    subject_id: str
    payload_hash: str
    ts: int
    entry_hash: str


def _entry_hash(seq, prev_hash, event_type, subject_id, payload_hash, ts) -> str:
    material = canonical_json([seq, prev_hash, event_type, subject_id, payload_hash, ts])
    return b64u(hashlib.sha256(material).digest())


class Ledger:
    def __init__(self, key: KeyPair):
        self._key = key
        self.entries: list[Entry] = []

    def append(self, event_type: str, subject_id: str, payload: dict, ts: int) -> Entry:
        seq = len(self.entries)
        prev = self.entries[-1].entry_hash if self.entries else GENESIS
        ph = sha256_b64u(canonical_json(payload))
        e = Entry(seq, prev, event_type, subject_id, ph, ts, _entry_hash(seq, prev, event_type, subject_id, ph, ts))
        self.entries.append(e)
        return e

    def checkpoint(self, ts: int) -> str:
        head = self.entries[-1]
        return jws_sign({"seq": head.seq, "entry_hash": head.entry_hash, "iat": ts}, self._key, CHECKPOINT_TYP)


def verify_chain(entries: list[Entry], checkpoint: str, jwks: dict) -> None:
    """Independently verify a contiguous ledger slice from genesis up to a signed checkpoint."""
    cp = jws_verify(checkpoint, jwks, CHECKPOINT_TYP)
    prev = GENESIS
    for i, e in enumerate(entries):
        if e.seq != i or e.prev_hash != prev:
            raise VerificationError("ledger_broken_link", f"seq {e.seq}")
        if _entry_hash(e.seq, e.prev_hash, e.event_type, e.subject_id, e.payload_hash, e.ts) != e.entry_hash:
            raise VerificationError("ledger_entry_tampered", f"seq {e.seq}")
        prev = e.entry_hash
    if not entries or entries[-1].seq != cp["seq"] or entries[-1].entry_hash != cp["entry_hash"]:
        raise VerificationError("ledger_checkpoint_mismatch")
