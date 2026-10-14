"""Merchant-side verifier (protocol-spec §1.3 and §3.3). Verification is offline apart from cached directory data."""
from __future__ import annotations

from dataclasses import dataclass

from .crypto import VerificationError, canonical_json, jws_verify, sha256_b64u
from .httpsig import HttpRequest, verify_request
from .server import DIRECTORY_PREFIX, TRUST_TIERS, TYP_TX, AgentPass

MAX_STATUS_STALENESS = 300


def cart_hash(cart: dict) -> str:
    return sha256_b64u(canonical_json(cart))


@dataclass
class AgentContext:
    agent_id: str
    operator_id: str
    operator_tier: str
    keyid: str


@dataclass
class PurchaseContext(AgentContext):
    jti: str
    user_ppid: str
    mandate_id: str
    amount: int
    amr: list[str]
    risk_tier: str


class MerchantVerifier:
    def __init__(self, ap: AgentPass, merchant_id: str, authority: str, min_operator_tier: str = "registered"):
        # `ap` stands in for HTTPS fetches of JWKS, agent directory and status list.
        self.ap = ap
        self.merchant_id = merchant_id
        self.authority = authority
        self.min_operator_tier = min_operator_tier
        self._seen_nonces: dict[str, int] = {}
        self._used_jti: set[str] = set()
        self.refresh()

    def refresh(self) -> None:
        self.jwks = self.ap.jwks()
        self.status = self.ap.status_snapshot()

    def verify_agent(self, req: HttpRequest) -> AgentContext:
        """Step ①: who is calling (enough for browsing)."""
        if req.authority != self.authority:
            raise VerificationError("wrong_authority")
        sig = verify_request(req, self.ap.resolve_agent_key, self.ap.now())
        now = self.ap.now()
        self._seen_nonces = {n: e for n, e in self._seen_nonces.items() if e >= now}
        if sig.nonce in self._seen_nonces:
            raise VerificationError("replayed_request")
        self._seen_nonces[sig.nonce] = sig.expires
        info = self.ap.agent_info(sig.agent_url[len(DIRECTORY_PREFIX):])
        if TRUST_TIERS.index(info["operator_tier"]) < TRUST_TIERS.index(self.min_operator_tier):
            raise VerificationError("operator_tier_too_low")
        return AgentContext(info["agent_id"], info["operator_id"], info["operator_tier"], sig.keyid)

    def verify_purchase(self, req: HttpRequest, server_cart: dict) -> PurchaseContext:
        """Steps ①②③: agent identity, delegation via Tx Token, and this exact cart."""
        agent = self.verify_agent(req)
        token = req.header("agentpass-transaction")
        if not token:
            raise VerificationError("missing_transaction_token")
        claims = jws_verify(token, self.jwks, TYP_TX)
        now = self.ap.now()
        if claims["exp"] < now - 60:
            raise VerificationError("token_expired")
        if claims["aud"] != self.merchant_id:
            raise VerificationError("wrong_audience")
        if claims["cnf"]["jkt"] != agent.keyid:
            raise VerificationError("token_binding_mismatch")
        if claims["act"]["sub"] != agent.agent_id:
            raise VerificationError("actor_mismatch")
        if cart_hash(server_cart) != claims["cart_hash"]:
            raise VerificationError("cart_mismatch")
        if server_cart["total"] > claims["amount"]["value"] or server_cart["currency"] != claims["amount"]["currency"]:
            raise VerificationError("amount_exceeds_authorized")
        if now - self.status["issued_at"] > MAX_STATUS_STALENESS:
            raise VerificationError("status_stale")  # fail closed (system-architecture §5)
        if claims["mandate_id"] in self.status["revoked"]:
            raise VerificationError("mandate_revoked")
        if claims["jti"] in self._used_jti:
            raise VerificationError("token_replayed")
        self._used_jti.add(claims["jti"])
        return PurchaseContext(agent.agent_id, agent.operator_id, agent.operator_tier, agent.keyid, claims["jti"], claims["sub"],
                               claims["mandate_id"], claims["amount"]["value"], claims["amr"], claims["risk"]["tier"])
