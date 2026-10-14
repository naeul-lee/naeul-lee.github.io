# AgentPass 프로토콜 명세 v0.1 (Draft)

이 문서의 "MUST / SHOULD / MAY" 는 RFC 2119 의미를 따른다.

## 0. 용어

| 용어 | 정의 |
|---|---|
| Operator | 에이전트를 운영하는 법인. OAuth `client_id` 에 대응 |
| Agent Instance | 실제 요청을 보내는 실행체. 고유 Ed25519 키 보유 |
| Mandate | 사용자 → 에이전트 위임을 표현하는 AgentPass 서명 JWT |
| Transaction Token (Tx Token) | Mandate로부터 교환된, 단일 거래에 고정된 단명 토큰 |
| Verifier | 머천트(또는 CDN 에지)의 검증기 |
| `jkt` | RFC 7638 JWK SHA-256 썸프린트 (base64url) |

공통 규칙:
- 서명 알고리즘: `EdDSA`(Ed25519) MUST 지원, `ES256` SHOULD 지원. `none`, `HS*` 금지.
- 모든 JWT 헤더는 `typ` 과 `kid` 를 MUST 포함. Verifier는 `typ` 을 MUST 검사(토큰 혼동 공격 방지).
- 시계 오차 허용: ±60초.
- 금액은 **최소 통화 단위 정수** (`KRW` 원, `USD` 센트).

---

## 1. Agent Identity

### 1.1 Instance Assertion (운영사 → 인스턴스)

```json
// header
{ "alg": "EdDSA", "typ": "agentpass-instance+jwt", "kid": "op_01J…#k1" }
// payload
{
  "iss": "op_01JBQ…",                 // operator id
  "sub": "agt_01JBR…",                // agent instance id
  "software_id": "shopbot-agent",
  "software_version": "2.3.1",
  "cnf": { "jwk": { "kty": "OKP", "crv": "Ed25519", "x": "…" } },
  "iat": 1792000000,
  "exp": 1792086400                   // ≤ iat + 24h (MUST)
}
```

### 1.2 Agent Directory

- `GET https://{agentpass}/.well-known/agentpass/agents/{agent_id}` → `{ agent_id, operator_id, operator_tier, jwk, status, exp }`
- `GET https://{agentpass}/.well-known/agentpass/jwks` → AgentPass 발급 키(JWKS)
- 응답은 `Cache-Control: max-age=60` 수준으로 캐시 가능. Verifier는 미지의 `keyid` 수신 시 1회 재조회 MAY.

### 1.3 HTTP 요청 서명 프로파일 (RFC 9421, Web Bot Auth 호환)

에이전트 → 머천트의 **모든** 요청은 서명 MUST.

```http
POST /checkout/confirm HTTP/1.1
Host: shop.example
Content-Type: application/json
Content-Digest: sha-256=:X48E9qOokqqrvdts8nOJRJN3OWDUoyWxBf7kbu9DBPE=:
Signature-Agent: "https://agentpass.example/.well-known/agentpass/agents/agt_01JBR…"
AgentPass-Transaction: eyJhbGciOiJFZERTQSIsInR5cCI6ImFnZW50cGFzcy10eCtqd3QiLC…
Signature-Input: ap=("@method" "@authority" "@path" "content-digest" "signature-agent" "agentpass-transaction");created=1792000123;expires=1792000183;keyid="<instance jkt>";nonce="b3k2…";alg="ed25519";tag="agentpass"
Signature: ap=:base64(signature):
```

| 규칙 | 내용 |
|---|---|
| 서명 대상 컴포넌트 | `@method`, `@authority`, `@path`, `signature-agent` MUST. 본문이 있으면 `content-digest` MUST. Tx Token이 있으면 `agentpass-transaction` MUST |
| `keyid` | 인스턴스 키의 `jkt` |
| `created`/`expires` | `expires - created ≤ 300`, 수신 시각이 범위 밖이면 거부 |
| `nonce` | 128비트 이상 랜덤. Verifier는 `expires` 까지 재사용 탐지 SHOULD (구매 계열 요청은 MUST) |
| `tag` | `"agentpass"` 고정 |

**검증 절차 (Verifier)**
1. `Signature-Agent` 디렉토리 조회(캐시) → 인스턴스 `status=active`, 미만료, `jkt == keyid` 확인.
2. RFC 9421 서명 베이스 재구성 → 서명 검증.
3. `content-digest` 를 본문으로 재계산·비교.
4. 시간 범위·nonce 검사.
5. 머천트 정책: `operator_tier ≥ min_operator_tier`.

---

## 2. Mandate

### 2.1 발급 요청 (RAR, RFC 9396)

```json
"authorization_details": [{
  "type": "agentpass_mandate",
  "actions": ["browse", "purchase", "order.read"],
  "constraints": { … §2.3 … },
  "delegation": { "allowed": true, "max_depth": 1 }
}]
```

### 2.2 Mandate JWT

```json
// header
{ "alg": "EdDSA", "typ": "agentpass-mandate+jwt", "kid": "ap-kr-2026-10" }
// payload
{
  "iss": "https://agentpass.example",
  "jti": "mdt_kr_01JBS…",
  "sub": "usr_01JB…",                   // AgentPass 내부 사용자 ID (머천트에 직접 제시하지 않음)
  "azp": "op_01JBQ…",                   // 위임받은 운영사
  "cnf": { "jkt": "…" },                // 선택: 특정 인스턴스로 고정. 없으면 운영사의 활성 인스턴스 누구나 교환 가능
  "actions": ["browse", "purchase", "order.read"],
  "constraints": { … },
  "delegation": { "allowed": true, "max_depth": 1, "depth": 0, "parent": null },
  "consent": {
    "summary_hash": "base64url(SHA-256(summary ‖ 0x00 ‖ JCS(constraints)))",
    "method": "webauthn",
    "locale": "ko-KR"
  },
  "status": { "status_list": { "uri": "https://agentpass.example/status/kr/7", "idx": 4211 } },
  "iat": 1792000000, "nbf": 1792000000, "exp": 1799776000
}
```

Mandate는 **에이전트만 보유**하며 머천트에 직접 제시하지 않는다(머천트에는 Tx Token만). 이는 사용자 전체 한도·다른 머천트 정보 노출을 막는다.

### 2.3 `constraints` 스키마

```json
{
  "currency": "KRW",
  "max_amount_per_tx": 50000,
  "max_amount_per_period": { "period": "P1M", "amount": 200000 },
  "max_tx_count": 20,
  "merchants": { "allow": ["mch_01…", "*.coupang.example"], "deny": [] },
  "categories": { "allow": ["grocery", "household"] },
  "shipping": { "address_ref": "addr_01…", "allow_change": false },
  "human_presence": "not_required",      // "not_required" | "required_over_amount" | "always"
  "stepup_over_amount": 50000,
  "valid_hours": { "tz": "Asia/Seoul", "from": "07:00", "to": "23:00" }
}
```

**Attenuation 규칙 (재위임·교환 시)**: 자식 값은 부모 값보다 MUST 엄격해야 한다.
숫자 한도 ≤ 부모, 허용목록 ⊆ 부모, 거부목록 ⊇ 부모, 기간 ⊆ 부모, `actions` ⊆ 부모, `depth = 부모 depth + 1 ≤ max_depth`.

---

## 3. Transaction Token

### 3.1 교환 요청 (RFC 8693)

```http
POST /oauth2/token
DPoP: <에이전트 인스턴스 키로 서명한 DPoP proof>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=<mandate>
&subject_token_type=urn:agentpass:token-type:mandate
&actor_token=<instance assertion>
&actor_token_type=urn:agentpass:token-type:instance
&requested_token_type=urn:agentpass:token-type:transaction
&authorization_details=[{"type":"agentpass_transaction","merchant_id":"mch_01…","action":"purchase",
   "amount":{"value":32900,"currency":"KRW"},"cart_hash":"…","category":"household"}]
```

응답:
- `200` → `{ access_token: <tx token>, issued_token_type, expires_in: 300, payment_credential?: {...} }`
- `403 {"error":"step_up_required","auth_req_id":"…","interval":5,"expires_in":300}`
- `403 {"error":"mandate_constraint_violation","violations":["max_amount_per_tx"]}`
- `401 {"error":"invalid_mandate"|"mandate_revoked"|"agent_binding_mismatch"}`

### 3.2 Tx Token JWT

```json
// header
{ "alg": "EdDSA", "typ": "agentpass-tx+jwt", "kid": "ap-kr-2026-10" }
// payload
{
  "iss": "https://agentpass.example",
  "jti": "txn_01JBT…",
  "aud": "mch_01…",
  "sub": "ppid_8f2c…",                  // 머천트별 pairwise 가명 ID (HMAC(user, merchant))
  "act": { "sub": "agt_01JBR…", "op": "op_01JBQ…", "tier": "verified" },
  "mandate_id": "mdt_kr_01JBS…",
  "action": "purchase",
  "amount": { "value": 32900, "currency": "KRW" },
  "cart_hash": "base64url(SHA-256(JCS(cart)))",
  "cnf": { "jkt": "<instance jkt>" },
  "amr": ["mandate"],                   // step-up 시 ["mandate","stepup_webauthn"]
  "risk": { "tier": "low", "score": 0.12 },
  "iat": 1792000123, "exp": 1792000423
}
```

### 3.3 Verifier 검증 절차 (머천트, 오프라인)

1. §1.3 HTTP 서명 검증 통과.
2. `typ == agentpass-tx+jwt`, AgentPass JWKS로 서명 검증, `exp/iat`.
3. `aud == 내 merchant_id`.
4. **`cnf.jkt == HTTP 서명 keyid`** (토큰 탈취 방지의 핵심).
5. `act.sub == Signature-Agent 의 agent_id`.
6. 서버가 계산한 `JCS(cart)` 해시 == `cart_hash`, 청구 금액 ≤ `amount.value`.
7. `jti` 미사용 확인 후 사용 처리 (1회용).
8. (선택) 고액 거래는 `POST /introspect` 로 실시간 상태 확인.
9. 결제 후 `POST /transactions/{jti}/capture`.

### 3.4 Cart 정규화

`cart_hash = base64url(SHA-256(JCS(cart)))`, JCS = RFC 8785. `cart` 최소 필드:
```json
{ "merchant_id": "mch_01…", "currency": "KRW",
  "items": [{ "sku": "W-2L-12", "qty": 1, "unit_price": 12900, "category": "grocery" }],
  "shipping": 3000, "discount": 0, "total": 15900, "quote_id": "q_…", "quote_exp": 1792000600 }
```

---

## 4. 철회 상태 (Status List)

- IETF Token Status List 형식(1bit/항목: 0=valid, 1=revoked), ZLIB 압축, AgentPass 서명 JWT로 배포.
- 30초마다 재발행, `ttl` 클레임 60초.
- Webhook: `mandate.revoked`, `agent.revoked`, `operator.suspended` (HMAC 서명 헤더 `AgentPass-Signature`).

## 5. 감사 영수증 (Receipt)

```
entry_hash_n = SHA-256( seq_n ‖ entry_hash_{n-1} ‖ event_type ‖ subject_id ‖ payload_hash ‖ ts )
```
- 1분마다 `checkpoint = Sign_AgentPass(seq, entry_hash)` 발행, 외부 투명성 로그에 게시.
- **Evidence Bundle** (`GET /transactions/{jti}/evidence`): Mandate(머천트용 축약본, SD-JWT로 constraints 일부만 공개), 사용자 승인 WebAuthn assertion 해시, Tx Token, cart, HTTP 서명 원본, 해당 엔트리부터 다음 체크포인트까지의 해시 경로.

## 6. 외부 프로토콜 매핑

| AgentPass | AP2 | Visa TAP / Web Bot Auth | Mastercard Agent Pay | ACP |
|---|---|---|---|---|
| Instance Assertion + HTTP 서명 | — | 에이전트 서명 요청 (RFC 9421) | KYA 등록 에이전트 | 에이전트 식별 헤더 |
| Mandate (반복형) | Intent Mandate | 소비자 인가 | 소비자 권한·한도 | — |
| Tx Token (cart_hash) | Cart Mandate | — | Verifiable Intent | Checkout session |
| Payment Credential Broker | Payment Mandate | Visa 토큰 | Agentic Token | Shared Payment Token |

어댑터는 AgentPass 객체 → 상대 형식 변환 + 상대 형식 검증을 담당하며, 원 증빙은 Evidence Bundle에 함께 보관한다.
