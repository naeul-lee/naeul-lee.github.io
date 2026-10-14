"""Agent-side SDK: operator signing of instance assertions, request signing, DPoP proofs, token exchange."""
from __future__ import annotations

import json
import secrets

from .crypto import KeyPair, jws_sign, sha256_b64u
from .httpsig import HttpRequest, sign_request
from .server import DIRECTORY_PREFIX, INSTANCE_MAX_LIFETIME, ISSUER, TYP_DPOP, TYP_INSTANCE, AgentPass


class OperatorClient:
    def __init__(self, ap: AgentPass, name: str, domain: str, tier: str = "verified"):
        self.ap = ap
        self.name = name
        self.key = KeyPair.generate()
        self.id = ap.register_operator(name, domain, self.key.public_jwk, tier)
        self.key.kid = f"{self.id}#k1"

    def launch_instance(self, lifetime: int = INSTANCE_MAX_LIFETIME) -> "AgentInstance":
        return AgentInstance(self, lifetime)


class AgentInstance:
    def __init__(self, operator: OperatorClient, lifetime: int):
        self.ap = operator.ap
        self.operator = operator
        self.key = KeyPair.generate()
        self.key.kid = self.key.jkt
        self.id = f"agt_{self.key.jkt[:16]}"
        now = self.ap.now()
        self.assertion = jws_sign({
            "iss": operator.id, "sub": self.id, "software_id": f"{operator.name.lower()}-agent",
            "cnf": {"jwk": self.key.public_jwk}, "iat": now, "exp": now + lifetime,
        }, operator.key, TYP_INSTANCE)
        self.ap.register_instance(self.assertion)

    @property
    def directory_url(self) -> str:
        return DIRECTORY_PREFIX + self.id

    def dpop(self, subject_token: str, htu: str = f"{ISSUER}/oauth2/token") -> str:
        return jws_sign({"htm": "POST", "htu": htu, "iat": self.ap.now(), "jti": secrets.token_urlsafe(12),
                         "ath": sha256_b64u(subject_token.encode())}, self.key, TYP_DPOP)

    def exchange(self, mandate: str, details: dict, auth_req_id: str | None = None) -> dict:
        return self.ap.exchange(mandate, self.assertion, self.dpop(mandate), details, auth_req_id)

    def request(self, method: str, authority: str, path: str, body: dict | None = None,
                tx_token: str | None = None) -> HttpRequest:
        headers = {"content-type": "application/json"} if body is not None else {}
        if tx_token:
            headers["agentpass-transaction"] = tx_token
        req = HttpRequest(method, authority, path, headers, json.dumps(body).encode() if body is not None else b"")
        return sign_request(req, self.key, self.directory_url, self.ap.now())
