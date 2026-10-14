"""End-to-end protocol tests. Test names map to docs/03-architecture/threat-model.md."""
import base64
import copy
import unittest

from agentpass.agent import OperatorClient
from agentpass.crypto import KeyPair, VerificationError
from agentpass.ledger import verify_chain
from agentpass.merchant import MerchantVerifier, cart_hash
from agentpass.server import AgentPass, ConstraintViolation, StepUpRequired

MERCHANT = "mch_market_a"
HOST = "market-a.example"

CONSTRAINTS = {
    "currency": "KRW",
    "max_amount_per_tx": 100000,
    "max_amount_per_period": {"period": "P1M", "amount": 200000},
    "max_tx_count": 20,
    "merchants": {"allow": [MERCHANT, "mch_market_b"]},
    "categories": {"allow": ["grocery", "household"]},
    "stepup_over_amount": 50000,
}


class Clock:
    def __init__(self, t: int):
        self.t = t

    def __call__(self) -> int:
        return self.t


def make_cart(total: int, category: str = "household", merchant: str = MERCHANT) -> dict:
    return {"merchant_id": merchant, "currency": "KRW", "quote_id": f"q_{total}_{category}",
            "items": [{"sku": "TISSUE-30", "qty": 1, "unit_price": total, "category": category}],
            "shipping": 0, "discount": 0, "total": total}


def details_for(cart: dict, action: str = "purchase") -> dict:
    return {"merchant_id": cart["merchant_id"], "action": action, "category": cart["items"][0]["category"],
            "amount": {"value": cart["total"], "currency": cart["currency"]}, "cart_hash": cart_hash(cart)}


class AgentPassFlowTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(1792000000)
        self.ap = AgentPass(self.clock)
        self.user_key = KeyPair.generate()
        self.user = self.ap.register_user(self.user_key.public_jwk)
        self.op = OperatorClient(self.ap, "ShopBot", "shopbot.example")
        self.agent = self.op.launch_instance()
        self.mandate = self.grant(self.op, ["browse", "purchase", "order.read"], CONSTRAINTS,
                                  {"allowed": True, "max_depth": 1})
        self.merchant = MerchantVerifier(self.ap, MERCHANT, HOST)

    # helpers ---------------------------------------------------------------
    def grant(self, op, actions, constraints, delegation=None):
        pending = self.ap.begin_mandate(self.user, op.id, actions, constraints, delegation)
        return self.ap.approve_mandate(pending["request_id"], self.user_key.sign(pending["challenge"]))

    def checkout(self, agent, cart, mandate=None):
        tok = agent.exchange(mandate or self.mandate, details_for(cart))["access_token"]
        return tok, agent.request("POST", HOST, "/checkout/confirm", {"quote_id": cart["quote_id"]}, tx_token=tok)

    def buy(self, total, agent=None, mandate=None, category="household"):
        agent = agent or self.agent
        cart = make_cart(total, category)
        _, req = self.checkout(agent, cart, mandate)
        ctx = self.merchant.verify_purchase(req, cart)
        self.ap.capture(MERCHANT, ctx.jti, cart["total"])
        return ctx

    def assertCode(self, code, fn, *args, **kwargs):
        with self.assertRaises(VerificationError) as cm:
            fn(*args, **kwargs)
        self.assertEqual(cm.exception.code, code, str(cm.exception))

    # happy paths -----------------------------------------------------------
    def test_consent_summary_generated_by_agentpass(self):
        pending = self.ap.begin_mandate(self.user, self.op.id, ["purchase"], CONSTRAINTS)
        self.assertIn("ShopBot", pending["summary"])
        self.assertIn("200,000 KRW", pending["summary"])
        self.assertIn("50,000 KRW 초과 시 매번 본인 승인", pending["summary"])

    def test_browse_requires_only_agent_identity(self):
        ctx = self.merchant.verify_agent(self.agent.request("GET", HOST, "/products?q=tissue"))
        self.assertEqual(ctx.operator_id, self.op.id)
        self.assertEqual(ctx.operator_tier, "verified")

    def test_happy_path_purchase(self):
        first = self.buy(32900)
        self.assertEqual(first.risk_tier, "medium")  # first purchase at this merchant -> notify user
        self.assertEqual(first.amr, ["mandate"])
        self.assertTrue(first.user_ppid.startswith("ppid_"))
        second = self.buy(12900)
        self.assertEqual(second.risk_tier, "low")

    def test_stepup_required_then_approved(self):
        cart = make_cart(72000)
        with self.assertRaises(StepUpRequired) as cm:
            self.agent.exchange(self.mandate, details_for(cart))
        stepup = cm.exception
        self.assertIn("72,000 KRW", stepup.binding_message)
        self.assertCode("authorization_pending", self.agent.exchange, self.mandate, details_for(cart), stepup.auth_req_id)
        self.ap.approve_stepup(stepup.auth_req_id, self.user, self.user_key.sign(stepup.challenge))
        tok = self.agent.exchange(self.mandate, details_for(cart), stepup.auth_req_id)["access_token"]
        req = self.agent.request("POST", HOST, "/checkout/confirm", {"quote_id": cart["quote_id"]}, tx_token=tok)
        ctx = self.merchant.verify_purchase(req, cart)
        self.assertEqual(ctx.amr, ["mandate", "stepup_webauthn"])

    def test_stepup_approval_cannot_be_reused_for_other_cart(self):
        cart = make_cart(72000)
        with self.assertRaises(StepUpRequired) as cm:
            self.agent.exchange(self.mandate, details_for(cart))
        self.ap.approve_stepup(cm.exception.auth_req_id, self.user, self.user_key.sign(cm.exception.challenge))
        self.assertCode("invalid_auth_req_id", self.agent.exchange, self.mandate,
                        details_for(make_cart(99000)), cm.exception.auth_req_id)

    def test_stepup_rejects_signature_from_other_key(self):
        cart = make_cart(72000)
        with self.assertRaises(StepUpRequired) as cm:
            self.agent.exchange(self.mandate, details_for(cart))
        self.assertCode("invalid_signature", self.ap.approve_stepup, cm.exception.auth_req_id, self.user,
                        KeyPair.generate().sign(cm.exception.challenge))

    # constraints (T11, T13) ------------------------------------------------
    def test_hard_ceiling_denied_even_with_stepup(self):
        with self.assertRaises(ConstraintViolation) as cm:
            self.agent.exchange(self.mandate, details_for(make_cart(150000)))
        self.assertIn("max_amount_per_tx", cm.exception.violations)

    def test_cumulative_limit_enforced(self):
        for _ in range(4):
            self.buy(45000)  # 180,000 captured
        with self.assertRaises(ConstraintViolation) as cm:
            self.agent.exchange(self.mandate, details_for(make_cart(45000)))
        self.assertEqual(cm.exception.violations, ["max_amount_per_period"])

    def test_outstanding_reservations_count_toward_limit(self):
        for _ in range(4):
            self.agent.exchange(self.mandate, details_for(make_cart(45000)))  # issued, not captured
        with self.assertRaises(ConstraintViolation):
            self.agent.exchange(self.mandate, details_for(make_cart(45000)))

    def test_expired_reservation_releases_limit(self):
        for _ in range(4):
            self.agent.exchange(self.mandate, details_for(make_cart(45000)))
        self.clock.t += 301
        self.agent.exchange(self.mandate, details_for(make_cart(45000)))

    def test_merchant_not_allowed(self):
        with self.assertRaises(ConstraintViolation) as cm:
            self.agent.exchange(self.mandate, details_for(make_cart(10000, merchant="mch_attacker")))
        self.assertEqual(cm.exception.violations, ["merchants"])

    def test_category_not_allowed(self):
        with self.assertRaises(ConstraintViolation) as cm:
            self.agent.exchange(self.mandate, details_for(make_cart(10000, category="electronics")))
        self.assertEqual(cm.exception.violations, ["categories"])

    def test_action_not_granted(self):
        with self.assertRaises(ConstraintViolation) as cm:
            self.agent.exchange(self.mandate, details_for(make_cart(10000), action="order.return"))
        self.assertEqual(cm.exception.violations, ["action"])

    # identity & binding (T1, T2, T16) ------------------------------------
    def test_forged_signature_rejected(self):
        req = self.agent.request("GET", HOST, "/products")
        attacker = KeyPair.generate()
        req.headers["signature"] = "ap=:" + base64.b64encode(attacker.sign(b"x")).decode() + ":"
        self.assertCode("invalid_signature", self.merchant.verify_agent, req)

    def test_impersonation_with_own_key_rejected(self):
        attacker_op = OperatorClient(self.ap, "Evil", "evil.example")
        attacker = attacker_op.launch_instance()
        req = attacker.request("GET", HOST, "/products")
        req.headers["signature-agent"] = f'"{self.agent.directory_url}"'  # claim to be ShopBot
        self.assertCode("agent_not_active", self.merchant.verify_agent, req)

    def test_stolen_token_other_agent_rejected(self):
        cart = make_cart(20000)
        tok, _ = self.checkout(self.agent, cart)
        other = self.op.launch_instance()  # same operator, different instance key
        req = other.request("POST", HOST, "/checkout/confirm", {"quote_id": cart["quote_id"]}, tx_token=tok)
        self.assertCode("token_binding_mismatch", self.merchant.verify_purchase, req, cart)

    def test_mandate_unusable_by_other_operator(self):
        thief = OperatorClient(self.ap, "Thief", "thief.example").launch_instance()
        self.assertCode("agent_binding_mismatch", thief.exchange, self.mandate, details_for(make_cart(1000)))

    def test_mandate_unusable_without_instance_key(self):
        other = self.op.launch_instance()
        # Present ShopBot's assertion but sign DPoP with another key: proof kid doesn't match the instance key.
        self.assertCode("unknown_kid", self.ap.exchange, self.mandate, self.agent.assertion,
                        other.dpop(self.mandate), details_for(make_cart(1000)))

    def test_dpop_proof_replay_rejected(self):
        proof = self.agent.dpop(self.mandate)
        self.ap.exchange(self.mandate, self.agent.assertion, proof, details_for(make_cart(1000)))
        self.assertCode("dpop_replay", self.ap.exchange, self.mandate, self.agent.assertion, proof,
                        details_for(make_cart(1000)))

    def test_revoked_instance_rejected(self):
        self.ap.revoke_instance(self.agent.id)
        self.assertCode("agent_not_active", self.merchant.verify_agent, self.agent.request("GET", HOST, "/products"))
        self.assertCode("agent_not_active", self.agent.exchange, self.mandate, details_for(make_cart(1000)))

    def test_instance_lifetime_capped(self):
        self.assertCode("instance_lifetime_invalid", self.op.launch_instance, 48 * 3600)

    def test_operator_tier_policy(self):
        strict = MerchantVerifier(self.ap, MERCHANT, HOST, min_operator_tier="certified")
        self.assertCode("operator_tier_too_low", strict.verify_agent, self.agent.request("GET", HOST, "/products"))

    # integrity & replay (T3, T4, T12) ---------------------------------------
    def test_tampered_body_rejected(self):
        req = self.agent.request("POST", HOST, "/checkout/confirm", {"ship_to": "home"})
        req.body = b'{"ship_to": "attacker"}'
        self.assertCode("digest_mismatch", self.merchant.verify_agent, req)

    def test_tampered_path_rejected(self):
        req = self.agent.request("GET", HOST, "/orders/1")
        req.path = "/orders/2"
        self.assertCode("invalid_signature", self.merchant.verify_agent, req)

    def test_cart_swap_rejected(self):
        cart = make_cart(20000)
        _, req = self.checkout(self.agent, cart)
        swapped = copy.deepcopy(cart)
        swapped["items"][0]["sku"] = "TV-65"
        self.assertCode("cart_mismatch", self.merchant.verify_purchase, req, swapped)

    def test_replay_rejected(self):
        cart = make_cart(20000)
        tok, req = self.checkout(self.agent, cart)
        self.merchant.verify_purchase(req, cart)
        self.assertCode("replayed_request", self.merchant.verify_purchase, req, cart)
        fresh = self.agent.request("POST", HOST, "/checkout/confirm", {"quote_id": cart["quote_id"]}, tx_token=tok)
        self.assertCode("token_replayed", self.merchant.verify_purchase, fresh, cart)

    def test_expired_signature_rejected(self):
        req = self.agent.request("GET", HOST, "/products")
        self.clock.t += 400
        self.assertCode("signature_expired", self.merchant.verify_agent, req)

    def test_wrong_audience_rejected(self):
        cart = make_cart(20000, merchant="mch_market_b")
        tok = self.agent.exchange(self.mandate, details_for(cart))["access_token"]
        req = self.agent.request("POST", HOST, "/checkout/confirm", {}, tx_token=tok)
        self.assertCode("wrong_audience", self.merchant.verify_purchase, req, cart)

    def test_mandate_cannot_be_used_as_tx_token(self):
        req = self.agent.request("POST", HOST, "/checkout/confirm", {}, tx_token=self.mandate)
        self.assertCode("wrong_token_type", self.merchant.verify_purchase, req, make_cart(1000))

    def test_capture_cannot_exceed_authorized(self):
        cart = make_cart(20000)
        _, req = self.checkout(self.agent, cart)
        ctx = self.merchant.verify_purchase(req, cart)
        self.assertCode("amount_exceeds_authorized", self.ap.capture, MERCHANT, ctx.jti, 25000)

    # revocation (T18) ------------------------------------------------------
    def test_revoked_mandate_rejected(self):
        cart = make_cart(20000)
        _, req = self.checkout(self.agent, cart)
        self.ap.revoke_mandate(self.ap.txs[next(iter(self.ap.txs))].mandate_id)
        self.merchant.refresh()  # status list / webhook
        self.assertCode("mandate_revoked", self.merchant.verify_purchase, req, cart)
        self.assertCode("mandate_revoked", self.agent.exchange, self.mandate, details_for(cart))

    def test_stale_status_fails_closed(self):
        cart = make_cart(20000)
        _, _ = self.checkout(self.agent, cart)
        self.clock.t += 301
        _, req = self.checkout(self.agent, cart)
        self.assertCode("status_stale", self.merchant.verify_purchase, req, cart)

    def test_consent_requires_users_passkey(self):
        pending = self.ap.begin_mandate(self.user, self.op.id, ["purchase"], CONSTRAINTS)
        self.assertCode("invalid_signature", self.ap.approve_mandate, pending["request_id"],
                        KeyPair.generate().sign(pending["challenge"]))

    # sub-delegation (T10) -------------------------------------------------
    def _child_agent(self):
        return OperatorClient(self.ap, "GroceryPro", "grocerypro.example").launch_instance()

    def test_subdelegation_within_scope(self):
        child = self._child_agent()
        narrow = {**CONSTRAINTS, "max_amount_per_tx": 30000, "max_amount_per_period": {"period": "P1M", "amount": 50000},
                  "stepup_over_amount": 30000, "merchants": {"allow": [MERCHANT]}, "categories": {"allow": ["grocery"]}}
        child_mandate = self.ap.subdelegate(self.mandate, self.agent.assertion, self.agent.dpop(self.mandate),
                                            child.assertion, ["purchase"], narrow)
        ctx = self.buy(15000, agent=child, mandate=child_mandate, category="grocery")
        self.assertEqual(ctx.agent_id, child.id)
        # The child mandate is bound to the child's instance key: the parent agent can't use it.
        self.assertCode("agent_binding_mismatch", self.agent.exchange, child_mandate, details_for(make_cart(1000, "grocery")))
        # Revoking the parent cascades.
        self.ap.revoke_mandate(self.ap.mandates[next(iter(self.ap.mandates))].id)
        self.assertCode("mandate_revoked", child.exchange, child_mandate, details_for(make_cart(1000, "grocery")))

    def test_subdelegation_cannot_escalate(self):
        child = self._child_agent()
        wider = {**CONSTRAINTS, "max_amount_per_tx": 500000, "categories": {"allow": ["grocery", "electronics"]}}
        with self.assertRaises(ConstraintViolation) as cm:
            self.ap.subdelegate(self.mandate, self.agent.assertion, self.agent.dpop(self.mandate),
                                child.assertion, ["purchase", "order.return"], wider)
        self.assertEqual(set(cm.exception.violations), {"actions", "max_amount_per_tx", "categories"})

    def test_subdelegation_depth_limited(self):
        child = self._child_agent()
        child_mandate = self.ap.subdelegate(self.mandate, self.agent.assertion, self.agent.dpop(self.mandate),
                                            child.assertion, ["purchase"], CONSTRAINTS)
        grandchild = self._child_agent()
        self.assertCode("delegation_not_allowed", self.ap.subdelegate, child_mandate, child.assertion,
                        child.dpop(child_mandate), grandchild.assertion, ["purchase"], CONSTRAINTS)

    # privacy (T8) ----------------------------------------------------------
    def test_pairwise_subject_per_merchant(self):
        a = self.ap._pairwise_sub(self.user, MERCHANT)
        b = self.ap._pairwise_sub(self.user, "mch_market_b")
        self.assertNotEqual(a, b)
        self.assertNotIn(self.user, a)

    # audit ledger (T5, T6) -------------------------------------------------
    def test_ledger_evidence_verifies(self):
        ctx = self.buy(20000)
        ev = self.ap.evidence(MERCHANT, ctx.jti)
        verify_chain(ev["ledger_entries"], ev["checkpoint"], self.merchant.jwks)
        types = [e.event_type for e in ev["ledger_entries"]]
        self.assertIn("mandate.issued", types)
        self.assertIn("token.exchanged", types)
        self.assertIn("tx.captured", types)

    def test_ledger_tamper_detected(self):
        ctx = self.buy(20000)
        ev = self.ap.evidence(MERCHANT, ctx.jti)
        entries = [copy.copy(e) for e in ev["ledger_entries"]]
        entries[2].payload_hash = "A" * 43
        self.assertCode("ledger_entry_tampered", verify_chain, entries, ev["checkpoint"], self.merchant.jwks)
        dropped = ev["ledger_entries"][:2] + ev["ledger_entries"][3:]
        self.assertCode("ledger_broken_link", verify_chain, dropped, ev["checkpoint"], self.merchant.jwks)


if __name__ == "__main__":
    unittest.main()
