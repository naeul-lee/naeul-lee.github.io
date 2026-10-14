"""Narrated end-to-end walkthrough of the AgentPass flows (python3 demo.py)."""
from agentpass.agent import OperatorClient
from agentpass.crypto import KeyPair, VerificationError, jws_decode_unverified
from agentpass.ledger import verify_chain
from agentpass.merchant import MerchantVerifier, cart_hash
from agentpass.server import AgentPass, ConstraintViolation, StepUpRequired

MERCHANT, HOST = "mch_market_a", "market-a.example"


def step(title):
    print(f"\n━━ {title}")


def cart(total, category="household"):
    return {"merchant_id": MERCHANT, "currency": "KRW", "quote_id": f"q_{total}", "shipping": 0, "discount": 0,
            "items": [{"sku": "TISSUE-30", "qty": 1, "unit_price": total, "category": category}], "total": total}


def details(c):
    return {"merchant_id": MERCHANT, "action": "purchase", "category": c["items"][0]["category"],
            "amount": {"value": c["total"], "currency": "KRW"}, "cart_hash": cart_hash(c)}


def main():
    ap = AgentPass()

    step("1. 에이전트 운영사 등록 + 인스턴스 기동 (KYA)")
    shopbot = OperatorClient(ap, "ShopBot", "shopbot.example")
    agent = shopbot.launch_instance()
    print(f"operator={shopbot.id} tier=verified  instance={agent.id}")

    step("2. 사용자(지은)가 패스키로 Mandate 발급")
    passkey = KeyPair.generate()
    jieun = ap.register_user(passkey.public_jwk)
    constraints = {"currency": "KRW", "max_amount_per_tx": 100000,
                   "max_amount_per_period": {"period": "P1M", "amount": 200000},
                   "merchants": {"allow": [MERCHANT]}, "categories": {"allow": ["grocery", "household"]},
                   "stepup_over_amount": 50000}
    pending = ap.begin_mandate(jieun, shopbot.id, ["browse", "purchase"], constraints)
    print("동의 화면:", pending["summary"])
    mandate = ap.approve_mandate(pending["request_id"], passkey.sign(pending["challenge"]))
    print("Mandate claims:", {k: v for k, v in jws_decode_unverified(mandate)[1].items() if k in ("jti", "azp", "actions")})

    merchant = MerchantVerifier(ap, MERCHANT, HOST)

    step("3. 상품 조회 — 에이전트 신원만 검증")
    print(merchant.verify_agent(agent.request("GET", HOST, "/products?q=tissue")))

    step("4. 32,900원 자동 구매 (사용자 부재)")
    c = cart(32900)
    tok = agent.exchange(mandate, details(c))["access_token"]
    ctx = merchant.verify_purchase(agent.request("POST", HOST, "/checkout/confirm", {"quote_id": c["quote_id"]}, tok), c)
    ap.capture(MERCHANT, ctx.jti, c["total"])
    print(f"승인: jti={ctx.jti} user={ctx.user_ppid} risk={ctx.risk_tier} amr={ctx.amr}")

    step("5. 72,000원 — Step-up 필요")
    c = cart(72000)
    try:
        agent.exchange(mandate, details(c))
    except StepUpRequired as s:
        print("푸시 알림:", s.binding_message)
        ap.approve_stepup(s.auth_req_id, jieun, passkey.sign(s.challenge))
        tok = agent.exchange(mandate, details(c), s.auth_req_id)["access_token"]
        ctx = merchant.verify_purchase(agent.request("POST", HOST, "/checkout/confirm", {}, tok), c)
        ap.capture(MERCHANT, ctx.jti, c["total"])
        print(f"승인: amr={ctx.amr}")

    step("6. 공격 시나리오")
    c = cart(20000)
    tok = agent.exchange(mandate, details(c))["access_token"]
    thief = shopbot.launch_instance()
    for name, fn in [
        ("탈취한 토큰을 다른 인스턴스가 사용", lambda: merchant.verify_purchase(
            thief.request("POST", HOST, "/checkout/confirm", {}, tok), c)),
        ("장바구니 바꿔치기", lambda: merchant.verify_purchase(
            agent.request("POST", HOST, "/checkout/confirm", {}, tok), cart(20000, "grocery"))),
        ("허용되지 않은 카테고리", lambda: agent.exchange(mandate, details(cart(9000, "electronics")))),
        ("월 누적 한도 초과", lambda: agent.exchange(mandate, details(cart(99000)))),
    ]:
        try:
            fn()
            print(f"  ✗ {name}: 통과됨 (예상 밖)")
        except (VerificationError, ConstraintViolation) as e:
            print(f"  ✓ {name}: 거부 ({e.code} {getattr(e, 'violations', '')})")

    step("7. 사용자가 Mandate 철회")
    ap.revoke_mandate(ctx.mandate_id)
    merchant.refresh()
    try:
        merchant.verify_purchase(agent.request("POST", HOST, "/checkout/confirm", {}, tok), c)
    except VerificationError as e:
        print("  ✓ 이미 발급된 토큰도 거부:", e.code)

    step("8. 분쟁 증빙 — 감사 원장 독립 검증")
    ev = ap.evidence(MERCHANT, ctx.jti)
    verify_chain(ev["ledger_entries"], ev["checkpoint"], ap.jwks())
    print(f"  ✓ {len(ev['ledger_entries'])}개 엔트리 해시 체인 + 서명 체크포인트 검증 완료")
    for e in ev["ledger_entries"]:
        print(f"    #{e.seq:02d} {e.event_type:<20} {e.subject_id}")


if __name__ == "__main__":
    main()
