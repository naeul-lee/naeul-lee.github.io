"""Minimal JOSE helpers: Ed25519 keys, JWK thumbprints, compact JWS, JCS-style canonical JSON."""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


class VerificationError(Exception):
    """Raised when any signature, token or protocol check fails. `code` is the protocol error code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def canonical_json(obj) -> bytes:
    # Approximates RFC 8785 (JCS) for the integer/string-only payloads used here.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_b64u(data: bytes) -> str:
    return b64u(hashlib.sha256(data).digest())


@dataclass
class KeyPair:
    private: Ed25519PrivateKey
    kid: str | None = None

    @classmethod
    def generate(cls, kid: str | None = None) -> "KeyPair":
        return cls(Ed25519PrivateKey.generate(), kid)

    @property
    def public_jwk(self) -> dict:
        raw = self.private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return {"kty": "OKP", "crv": "Ed25519", "x": b64u(raw)}

    @property
    def jkt(self) -> str:
        return jwk_thumbprint(self.public_jwk)

    def sign(self, data: bytes) -> bytes:
        return self.private.sign(data)


def jwk_thumbprint(jwk: dict) -> str:
    """RFC 7638 thumbprint over the required OKP members."""
    required = {k: jwk[k] for k in ("crv", "kty", "x")}
    return sha256_b64u(canonical_json(required))


def public_key_from_jwk(jwk: dict) -> Ed25519PublicKey:
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise VerificationError("unsupported_key", str(jwk.get("kty")))
    return Ed25519PublicKey.from_public_bytes(b64u_decode(jwk["x"]))


def verify_raw(jwk: dict, data: bytes, signature: bytes) -> None:
    try:
        public_key_from_jwk(jwk).verify(signature, data)
    except InvalidSignature:
        raise VerificationError("invalid_signature") from None


def jws_sign(payload: dict, key: KeyPair, typ: str) -> str:
    header = {"alg": "EdDSA", "typ": typ, "kid": key.kid}
    signing_input = f"{b64u(canonical_json(header))}.{b64u(canonical_json(payload))}"
    return f"{signing_input}.{b64u(key.sign(signing_input.encode()))}"


def jws_decode_unverified(token: str) -> tuple[dict, dict]:
    try:
        h, p, _ = token.split(".")
        return json.loads(b64u_decode(h)), json.loads(b64u_decode(p))
    except Exception:
        raise VerificationError("malformed_token") from None


def jws_verify(token: str, jwks: dict[str, dict], expected_typ: str) -> dict:
    """Verify a compact JWS against a kid->JWK map and enforce `typ` (prevents token confusion)."""
    header, payload = jws_decode_unverified(token)
    if header.get("alg") != "EdDSA":
        raise VerificationError("unsupported_alg", str(header.get("alg")))
    if header.get("typ") != expected_typ:
        raise VerificationError("wrong_token_type", f"expected {expected_typ}, got {header.get('typ')}")
    jwk = jwks.get(header.get("kid"))
    if jwk is None:
        raise VerificationError("unknown_kid", str(header.get("kid")))
    h, p, s = token.split(".")
    verify_raw(jwk, f"{h}.{p}".encode(), b64u_decode(s))
    return payload
