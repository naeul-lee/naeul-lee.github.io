"""In-memory AgentPass platform: registry, mandate service, token exchange, step-up, capture, revocation."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

from . import policy
from .crypto import (KeyPair, VerificationError, b64u, canonical_json, jwk_thumbprint, jws_decode_unverified,
                     jws_sign, jws_verify, sha256_b64u, verify_raw)
from .ledger import Ledger

ISSUER = "https://agentpass.example"
DIRECTORY_PREFIX = f"{ISSUER}/.well-known/agentpass/agents/"

TYP_INSTANCE = "agentpass-instance+jwt"
TYP_MANDATE = "agentpass-mandate+jwt"
TYP_TX = "agentpass-tx+jwt"
TYP_DPOP = "dpop+jwt"

INSTANCE_MAX_LIFETIME = 24 * 3600
TX_TOKEN_LIFETIME = 300
TRUST_TIERS = ["registered", "verified", "certified"]


class StepUpRequired(Exception):
    def __init__(self, auth_req_id: str, binding_message: str, challenge: bytes):
        super().__init__("step_up_required")
        self.auth_req_id = auth_req_id
        self.binding_message = binding_message
        self.challenge = challenge


class ConstraintViolation(VerificationError):
    def __init__(self, violations: list[str]):
        super().__init__("mandate_constraint_violation", ",".join(violations))
        self.violations = violations


@dataclass
class Operator:
    id: str
    name: str
    domain: str
    jwk: dict
    tier: str


@dataclass
class Instance:
    id: str
    operator_id: str
    jwk: dict
    jkt: str
    exp: int
    status: str = "active"


@dataclass
class MandateRecord:
    id: str
    user_id: str
    operator_id: str
    actions: list[str]
    constraints: dict
    parent_id: str | None
    depth: int
    jwt: str = ""
    status: str = "active"
    consent_summary: str = ""
    children: list[str] = field(default_factory=list)


@dataclass
class TxRecord:
    jti: str
    mandate_id: str
    merchant_id: str
    amount: int
    exp: int
    period: str
    status: str = "issued"
    captured: int = 0


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


class AgentPass:
    def __init__(self, clock=lambda: int(time.time())):
        self.now = clock
        self._key = KeyPair.generate(kid="ap-kr-2026-10")
        self._pairwise_secret = secrets.token_bytes(32)
        self.ledger = Ledger(self._key)
        self.operators: dict[str, Operator] = {}
        self.instances: dict[str, Instance] = {}
        self.users: dict[str, dict] = {}            # user_id -> passkey public JWK
        self.mandates: dict[str, MandateRecord] = {}
        self.txs: dict[str, TxRecord] = {}
        self._pending_consents: dict[str, dict] = {}
        self._stepups: dict[str, dict] = {}
        self._used_dpop: set[str] = set()

    # ---------------------------------------------------------------- discovery
    def jwks(self) -> dict[str, dict]:
        return {self._key.kid: self._key.public_jwk}

    def resolve_agent_key(self, agent_url: str, keyid: str) -> dict:
        """Signature-Agent directory lookup used by verifiers (normally an HTTPS GET + cache)."""
        if not agent_url.startswith(DIRECTORY_PREFIX):
            raise VerificationError("unknown_directory", agent_url)
        inst = self.instances.get(agent_url[len(DIRECTORY_PREFIX):])
        if inst is None or inst.status != "active" or inst.exp < self.now():
            raise VerificationError("agent_not_active")
        if inst.jkt != keyid or self.operators[inst.operator_id].tier == "suspended":
            raise VerificationError("agent_not_active", "keyid mismatch or operator suspended")
        return inst.jwk

    def agent_info(self, agent_id: str) -> dict:
        inst = self.instances[agent_id]
        return {"agent_id": inst.id, "operator_id": inst.operator_id, "operator_tier": self.operators[inst.operator_id].tier}

    def status_snapshot(self) -> dict:
        """Stand-in for the Token Status List: revoked mandate ids as of `issued_at`."""
        return {"revoked": {m.id for m in self.mandates.values() if m.status == "revoked"}, "issued_at": self.now()}

    # ---------------------------------------------------------------- registry
    def register_operator(self, name: str, domain: str, jwk: dict, tier: str = "verified") -> str:
        op = Operator(_id("op"), name, domain, jwk, tier)
        self.operators[op.id] = op
        self.ledger.append("operator.registered", op.id, {"domain": domain, "tier": tier}, self.now())
        return op.id

    def register_instance(self, assertion: str) -> str:
        _, claims = jws_decode_unverified(assertion)
        op = self.operators.get(claims.get("iss"))
        if op is None:
            raise VerificationError("unknown_operator")
        claims = jws_verify(assertion, {f"{op.id}#k1": op.jwk}, TYP_INSTANCE)
        if claims["exp"] - claims["iat"] > INSTANCE_MAX_LIFETIME or claims["exp"] < self.now():
            raise VerificationError("instance_lifetime_invalid")
        jwk = claims["cnf"]["jwk"]
        inst = Instance(claims["sub"], op.id, jwk, jwk_thumbprint(jwk), claims["exp"])
        self.instances[inst.id] = inst
        self.ledger.append("agent.registered", inst.id, {"operator": op.id, "jkt": inst.jkt}, self.now())
        return inst.id

    def revoke_instance(self, agent_id: str) -> None:
        self.instances[agent_id].status = "revoked"
        self.ledger.append("agent.revoked", agent_id, {}, self.now())

    def register_user(self, passkey_jwk: dict) -> str:
        uid = _id("usr")
        self.users[uid] = passkey_jwk
        return uid

    # ---------------------------------------------------------------- mandates
    def begin_mandate(self, user_id: str, operator_id: str, actions: list[str], constraints: dict,
                      delegation: dict | None = None, ttl: int = 90 * 86400) -> dict:
        """Authorization request (PAR+RAR). Returns the AgentPass-generated summary and WebAuthn challenge."""
        summary = policy.consent_summary(self.operators[operator_id].name, actions, constraints)
        summary_hash = sha256_b64u(summary.encode() + b"\x00" + canonical_json(constraints))
        req_id = _id("par")
        self._pending_consents[req_id] = dict(user_id=user_id, operator_id=operator_id, actions=actions,
                                              constraints=constraints, delegation=delegation or {"allowed": False},
                                              ttl=ttl, summary=summary, summary_hash=summary_hash)
        return {"request_id": req_id, "summary": summary, "challenge": summary_hash.encode()}

    def approve_mandate(self, request_id: str, webauthn_signature: bytes) -> str:
        """User approves with passkey (simulated as Ed25519 signature over the challenge)."""
        req = self._pending_consents.pop(request_id)
        verify_raw(self.users[req["user_id"]], req["summary_hash"].encode(), webauthn_signature)
        return self._issue_mandate(req["user_id"], req["operator_id"], req["actions"], req["constraints"],
                                   req["delegation"], req["ttl"], req["summary_hash"], parent=None, cnf_jkt=None,
                                   summary=req["summary"])

    def _issue_mandate(self, user_id, operator_id, actions, constraints, delegation, ttl, summary_hash,
                       parent: MandateRecord | None, cnf_jkt: str | None, summary: str = "", act: dict | None = None) -> str:
        now = self.now()
        rec = MandateRecord(f"mdt_kr_{secrets.token_hex(8)}", user_id, operator_id, actions, constraints,
                            parent.id if parent else None, parent.depth + 1 if parent else 0, consent_summary=summary)
        claims = {
            "iss": ISSUER, "jti": rec.id, "sub": user_id, "azp": operator_id,
            "actions": actions, "constraints": constraints,
            "delegation": {**delegation, "depth": rec.depth, "parent": rec.parent_id},
            "consent": {"summary_hash": summary_hash, "method": "webauthn" if not parent else "delegation"},
            "iat": now, "nbf": now, "exp": now + ttl,
        }
        if cnf_jkt:
            claims["cnf"] = {"jkt": cnf_jkt}
        if act:
            claims["act"] = act
        rec.jwt = jws_sign(claims, self._key, TYP_MANDATE)
        self.mandates[rec.id] = rec
        if parent:
            parent.children.append(rec.id)
        self.ledger.append("mandate.issued", rec.id, claims, now)
        return rec.jwt

    def revoke_mandate(self, mandate_id: str) -> None:
        rec = self.mandates[mandate_id]
        rec.status = "revoked"
        for jti, tx in self.txs.items():
            if tx.mandate_id == mandate_id and tx.status == "issued":
                tx.status = "voided"
        self.ledger.append("mandate.revoked", mandate_id, {}, self.now())
        for child in rec.children:
            self.revoke_mandate(child)

    # ---------------------------------------------------------------- token exchange
    def _verify_actor(self, actor_assertion: str, dpop_proof: str, subject_token: str, htu: str) -> Instance:
        """Actor = registered, active instance; DPoP-style proof shows possession of its key for this request."""
        _, claims = jws_decode_unverified(actor_assertion)
        inst = self.instances.get(claims.get("sub"))
        if inst is None or inst.status != "active" or inst.exp < self.now():
            raise VerificationError("agent_not_active")
        jws_verify(actor_assertion, {f"{inst.operator_id}#k1": self.operators[inst.operator_id].jwk}, TYP_INSTANCE)
        proof = jws_verify(dpop_proof, {inst.jkt: inst.jwk}, TYP_DPOP)
        if proof["htu"] != htu or abs(proof["iat"] - self.now()) > 60 or proof["ath"] != sha256_b64u(subject_token.encode()):
            raise VerificationError("invalid_dpop_proof")
        if proof["jti"] in self._used_dpop:
            raise VerificationError("dpop_replay")
        self._used_dpop.add(proof["jti"])
        return inst

    def _verify_mandate(self, mandate_jwt: str, inst: Instance) -> MandateRecord:
        claims = jws_verify(mandate_jwt, self.jwks(), TYP_MANDATE)
        if claims["exp"] < self.now() or claims["nbf"] > self.now() + 60:
            raise VerificationError("invalid_mandate", "expired")
        rec = self.mandates.get(claims["jti"])
        if rec is None:
            raise VerificationError("invalid_mandate")
        node = rec
        while node:  # any revoked ancestor invalidates the chain
            if node.status != "active":
                raise VerificationError("mandate_revoked")
            node = self.mandates.get(node.parent_id) if node.parent_id else None
        if claims["azp"] != inst.operator_id:
            raise VerificationError("agent_binding_mismatch", "operator")
        if "cnf" in claims and claims["cnf"]["jkt"] != inst.jkt:
            raise VerificationError("agent_binding_mismatch", "instance key")
        return rec

    @staticmethod
    def _period_key(constraints: dict, ts: int) -> str:
        return time.strftime("%Y-%m", time.gmtime(ts)) if constraints.get("max_amount_per_period", {}).get("period") == "P1M" else "all"

    def _usage(self, rec: MandateRecord, merchant_id: str, period: str) -> policy.Usage:
        u = policy.Usage()
        now = self.now()
        for tx in self.txs.values():
            if tx.mandate_id != rec.id:
                continue
            live = tx.status == "captured" or (tx.status == "issued" and tx.exp >= now)
            if not live:
                continue
            u.tx_count += 1
            if tx.period == period:
                u.period_spent += tx.captured if tx.status == "captured" else tx.amount
            if tx.merchant_id == merchant_id and tx.status == "captured":
                u.known_merchant = True
        return u

    def exchange(self, mandate_jwt: str, actor_assertion: str, dpop_proof: str, details: dict,
                 auth_req_id: str | None = None) -> dict:
        """RFC 8693 token exchange: Mandate -> Transaction Token for one merchant/cart/amount."""
        inst = self._verify_actor(actor_assertion, dpop_proof, mandate_jwt, f"{ISSUER}/oauth2/token")
        rec = self._verify_mandate(mandate_jwt, inst)
        tx = policy.TxRequest(details["merchant_id"], details["action"], details["amount"]["value"],
                              details["amount"]["currency"], details.get("category"))
        period = self._period_key(rec.constraints, self.now())
        usage = self._usage(rec, tx.merchant_id, period)
        violations = policy.check_constraints(rec.actions, rec.constraints, tx, usage)
        if violations:
            self.ledger.append("token.denied", rec.id, {"violations": violations, **details}, self.now())
            raise ConstraintViolation(violations)

        tier, score = policy.risk_tier(rec.constraints, tx, usage, self.operators[inst.operator_id].tier)
        amr = ["mandate"]
        if tier == "high":
            binding = f"{self.operators[inst.operator_id].name}: {tx.merchant_id}에서 {tx.amount:,} {tx.currency} 결제 승인?"
            challenge = sha256_b64u(binding.encode() + b"\x00" + details["cart_hash"].encode()).encode()
            if auth_req_id is None:
                rid = _id("ciba")
                self._stepups[rid] = {"mandate_id": rec.id, "challenge": challenge, "approved": False, "details": details}
                self.ledger.append("stepup.requested", rec.id, {"auth_req_id": rid, **details}, self.now())
                raise StepUpRequired(rid, binding, challenge)
            st = self._stepups.get(auth_req_id)
            if not st or st["mandate_id"] != rec.id or st["details"] != details:
                raise VerificationError("invalid_auth_req_id")
            if not st["approved"]:
                raise VerificationError("authorization_pending")
            del self._stepups[auth_req_id]
            amr.append("stepup_webauthn")

        now = self.now()
        jti = _id("txn")
        claims = {
            "iss": ISSUER, "jti": jti, "aud": tx.merchant_id, "sub": self._pairwise_sub(rec.user_id, tx.merchant_id),
            "act": {"sub": inst.id, "op": inst.operator_id, "tier": self.operators[inst.operator_id].tier},
            "mandate_id": rec.id, "action": tx.action,
            "amount": {"value": tx.amount, "currency": tx.currency}, "cart_hash": details["cart_hash"],
            "cnf": {"jkt": inst.jkt}, "amr": amr, "risk": {"tier": tier, "score": score},
            "iat": now, "exp": now + TX_TOKEN_LIFETIME,
        }
        self.txs[jti] = TxRecord(jti, rec.id, tx.merchant_id, tx.amount, now + TX_TOKEN_LIFETIME, period)
        self.ledger.append("token.exchanged", jti, claims, now)
        return {"access_token": jws_sign(claims, self._key, TYP_TX),
                "issued_token_type": "urn:agentpass:token-type:transaction",
                "expires_in": TX_TOKEN_LIFETIME,
                "payment_credential": {"provider": "sandbox_psp", "token": f"pt_{secrets.token_hex(6)}",
                                       "max_amount": {"value": tx.amount, "currency": tx.currency}}}

    def approve_stepup(self, auth_req_id: str, user_id: str, webauthn_signature: bytes) -> None:
        st = self._stepups[auth_req_id]
        if self.mandates[st["mandate_id"]].user_id != user_id:
            raise VerificationError("access_denied")
        verify_raw(self.users[user_id], st["challenge"], webauthn_signature)
        st["approved"] = True
        self.ledger.append("stepup.approved", st["mandate_id"], {"auth_req_id": auth_req_id}, self.now())

    def _pairwise_sub(self, user_id: str, merchant_id: str) -> str:
        return "ppid_" + b64u(hmac.new(self._pairwise_secret, f"{user_id}|{merchant_id}".encode(), hashlib.sha256).digest()[:16])

    # ---------------------------------------------------------------- sub-delegation
    def subdelegate(self, parent_jwt: str, parent_actor: str, parent_dpop: str, child_actor: str,
                    actions: list[str], constraints: dict) -> str:
        """Parent agent mints a narrower mandate bound to the child agent's instance key (UC-10)."""
        parent_inst = self._verify_actor(parent_actor, parent_dpop, parent_jwt, f"{ISSUER}/oauth2/token")
        parent = self._verify_mandate(parent_jwt, parent_inst)
        _, pclaims = jws_decode_unverified(parent_jwt)
        deleg = pclaims["delegation"]
        if not deleg.get("allowed") or parent.depth + 1 > deleg.get("max_depth", 0):
            raise VerificationError("delegation_not_allowed")
        v = policy.attenuation_violations(parent.actions, parent.constraints, actions, constraints)
        if v:
            raise ConstraintViolation(v)
        _, cclaims = jws_decode_unverified(child_actor)
        child = self.instances.get(cclaims.get("sub"))
        if child is None or child.status != "active":
            raise VerificationError("agent_not_active", "child")
        jws_verify(child_actor, {f"{child.operator_id}#k1": self.operators[child.operator_id].jwk}, TYP_INSTANCE)
        act = {"sub": child.id, "act": {"sub": parent_inst.id}}
        return self._issue_mandate(parent.user_id, child.operator_id, actions, constraints,
                                   {"allowed": deleg.get("max_depth", 0) > parent.depth + 1, "max_depth": deleg["max_depth"]},
                                   int(pclaims["exp"]) - self.now(), pclaims["consent"]["summary_hash"],
                                   parent=parent, cnf_jkt=child.jkt, act=act)

    # ---------------------------------------------------------------- merchant callbacks
    def capture(self, merchant_id: str, jti: str, final_amount: int, status: str = "captured") -> None:
        tx = self.txs.get(jti)
        if tx is None or tx.merchant_id != merchant_id:
            raise VerificationError("unknown_transaction")
        if tx.status != "issued":
            raise VerificationError("transaction_not_capturable", tx.status)
        if final_amount > tx.amount:
            raise VerificationError("amount_exceeds_authorized")
        tx.status, tx.captured = (status, final_amount) if status == "captured" else ("voided", 0)
        self.ledger.append("tx.captured", jti, {"final_amount": final_amount, "status": status}, self.now())

    def evidence(self, merchant_id: str, jti: str) -> dict:
        tx = self.txs[jti]
        if tx.merchant_id != merchant_id:
            raise VerificationError("access_denied")
        return {"jti": jti, "mandate_id": tx.mandate_id,
                "ledger_entries": list(self.ledger.entries), "checkpoint": self.ledger.checkpoint(self.now())}
