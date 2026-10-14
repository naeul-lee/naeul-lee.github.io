# 위협 모델 (STRIDE + 에이전트 특화 위협)

## 1. 보호 자산
- A1 사용자 Mandate (구매 권한 그 자체)
- A2 에이전트 인스턴스·운영사 서명 키
- A3 AgentPass 발급 서명 키 (Mandate / Tx Token / 체크포인트)
- A4 결제 자격증명 (PSP 토큰)
- A5 사용자 개인정보 (배송지, 연락처, 구매 내역)
- A6 감사 원장 무결성

## 2. 신뢰 경계
`User Wallet` ↔ `AgentPass` ↔ `Agent (운영사 인프라, LLM 포함)` ↔ `Merchant` ↔ `PSP`.
**에이전트는 부분 신뢰(semi-trusted)** 로 간주한다: 운영사는 선의일 수 있으나, LLM은 프롬프트 인젝션으로 조종될 수 있다.

## 3. 위협 목록

| ID | 분류 | 위협 | 영향 | 대응 | 프로토타입 검증 |
|---|---|---|---|---|---|
| T1 | Spoofing | 악성 봇이 유명 에이전트를 사칭 | High | RFC 9421 서명 필수, 키 디렉토리는 등록 운영사만 | ✅ `test_forged_signature_rejected` |
| T2 | Spoofing | 탈취한 Mandate/Tx Token을 다른 에이전트가 사용 | High | `cnf.jkt` 바인딩: 토큰 키 ≠ 요청 서명 키 → 거부 | ✅ `test_stolen_token_other_agent_rejected` |
| T3 | Tampering | 중간자가 요청 본문(금액·배송지) 변조 | High | `content-digest` 를 서명 대상에 포함 | ✅ `test_tampered_body_rejected` |
| T4 | Tampering | 승인 후 장바구니 바꿔치기 | High | Tx Token에 `cart_hash`, 머천트가 확정 시 재계산 비교 | ✅ `test_cart_swap_rejected` |
| T5 | Repudiation | 사용자 "그런 위임 한 적 없다" | Medium | 패스키 서명 + `consent_hash`(본 문구) + 원장 | ✅ `test_ledger_*` |
| T6 | Repudiation | 머천트/AgentPass가 기록 조작 | Medium | 해시 체인 + 서명 체크포인트 + 외부 공증(투명성 로그) | ✅ `test_ledger_tamper_detected` |
| T7 | Info Disclosure | 머천트에 과도한 개인정보 노출 | Medium | SD-JWT 선택적 공개, Tx Token에 PII 없음(가명 `sub`) | 설계 |
| T8 | Info Disclosure | 머천트 간 사용자 추적(상관관계) | Medium | 머천트별 pairwise `sub` (PPID) | ✅ (pairwise sub 구현) |
| T9 | DoS | 토큰 교환 API 폭주 | Medium | 운영사별 rate limit, 에지 검증은 오프라인 | 설계 |
| T10 | EoP | 재위임으로 권한 확대 | High | 부분집합 검사, `max_depth`, 부모 철회 연쇄 | ✅ `test_subdelegation_cannot_escalate` |
| T11 | EoP | 한도 우회 (동시 요청 이중 지출) | High | 홈 리전 단일 카운터, 원자적 check-and-reserve | ✅ `test_cumulative_limit_enforced` |
| T12 | Replay | 같은 Tx Token/요청 재전송 | High | `jti` 1회용, 서명 `created` ± 60초 + `nonce` | ✅ `test_replay_rejected` |
| T13 | 에이전트 특화 | **프롬프트 인젝션**으로 에이전트가 Mandate 범위 내 악성 구매(예: 공격자 머천트) | High | 머천트 허용목록·카테고리 제약 권장 기본값, 신규 머천트 Medium 등급 알림, 배송지 변경 시 Step-up | ✅ `test_merchant_not_allowed` |
| T14 | 에이전트 특화 | 에이전트가 사용자에게 오해 소지 있는 동의 문구 제시 | Medium | 동의 요약은 **AgentPass가 constraints로부터 생성**(에이전트 제공 문구 금지) | 설계 |
| T15 | 에이전트 특화 | Step-up 피로 공격(승인 요청 남발 → 무심코 승인) | Medium | Step-up 요청 rate limit, binding_message에 금액·머천트 명시, 연속 거절 시 Mandate 일시정지 | 설계 |
| T16 | 키 관리 | 인스턴스 키 유출 | High | ≤24h 수명, 즉시 폐기 API, TPM/Secure Enclave 권장 | ✅ `test_revoked_instance_rejected` |
| T17 | 키 관리 | AgentPass 발급 키 유출 | Critical | HSM, 리전별 키 분리, 키 회전, 비상 폐기 절차, 체크포인트 투명성 로그로 사후 탐지 | 운영 |
| T18 | 철회 | 철회 후 캐시된 상태로 거래 성공 | High | Tx Token 5분 수명 + 교환 시점 실시간 확인 + Status List ≤60s | ✅ `test_revoked_mandate_rejected` |

## 4. 잔여 위험
- 사용자가 지나치게 넓은 Mandate를 발급하는 위험 → 지갑 UX에서 "권장 한도" 기본값과 위험 경고로 완화.
- 운영사 자체가 악의적인 경우 → KYB, 신뢰 등급, 머천트 정책(`min_operator_tier`), 신고·정지 프로세스.
