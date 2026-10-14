# PRD — AgentPass v1

## 1. 페르소나

| ID | 페르소나 | 상황 |
|---|---|---|
| P1 | **지은 (사용자)** 34세 직장인 | "매주 생수·휴지 떨어지면 알아서 최저가로 사줘. 단 한 번에 5만원 넘으면 물어봐." |
| P2 | **ShopBot Inc. (에이전트 운영사)** | 쇼핑 에이전트 서비스. 머천트마다 봇 차단을 당해 스크래핑·계정 공유로 우회 중 |
| P3 | **마켓A (머천트)** | 에이전트 트래픽이 늘지만 좋은 봇/나쁜 봇 구분 불가. 차지백 증가 우려 |
| P4 | **PG사 / 카드사** | 에이전트 거래를 식별해 위험 모델에 반영하고 싶음 |

## 2. 핵심 유스케이스

| ID | 유스케이스 | 주 액터 |
|---|---|---|
| UC-1 | 에이전트 운영사 등록 및 KYA 검증 | Operator |
| UC-2 | 에이전트 인스턴스 키 발급·회전 | Agent |
| UC-3 | 사용자가 에이전트에 Mandate 발급 (한도·범위 설정, 패스키 서명) | User |
| UC-4 | 에이전트가 머천트에서 상품 조회 (신원만 검증, 위임 불필요) | Agent → Merchant |
| UC-5 | 에이전트가 Mandate 범위 내 구매 (사용자 부재) | Agent → Merchant |
| UC-6 | 한도 초과/이상 거래 → 사용자 Step-up 승인 후 구매 | Agent, User |
| UC-7 | 사용자가 Mandate 즉시 철회 | User |
| UC-8 | 계정 행위(주문 조회·반품 신청) 위임 | Agent → Merchant |
| UC-9 | 분쟁 시 증빙 번들 조회·검증 | Merchant, PSP |
| UC-10 | 다중 에이전트 위임 체인 (개인비서 에이전트 → 쇼핑 전문 에이전트) | Agent |

## 3. 기능 요구사항 (FR)

### 3.1 에이전트 신원 (Know Your Agent)
- **FR-ID-1** 운영사(Operator)는 법인 정보·도메인 소유 증명(DNS TXT 또는 `/.well-known`)으로 등록한다.
- **FR-ID-2** 운영사는 신뢰 등급을 가진다: `registered` < `verified`(KYB 완료) < `certified`(보안 심사 통과).
- **FR-ID-3** 에이전트 인스턴스는 운영사가 서명한 **Instance Assertion**으로 등록하며, 인스턴스 키 유효기간은 최대 24시간.
- **FR-ID-4** 모든 에이전트 → 머천트 요청은 RFC 9421로 서명한다. 서명 키는 공개 JWKS 디렉토리로 조회 가능해야 한다.
- **FR-ID-5** 운영사/인스턴스 키 폐기는 60초 내에 전 검증 노드에 반영된다.

### 3.2 위임 (Mandate)
- **FR-MD-1** Mandate는 다음 제약을 표현할 수 있다: 최대 1회 금액, 기간 누적 금액, 통화, 머천트 허용/차단 목록, 상품 카테고리, 유효기간, 사용 횟수, 허용 행위(scope: `browse`, `purchase`, `order.read`, `order.return` …), Human-presence 요구 여부.
- **FR-MD-2** Mandate 발급은 사용자 패스키(WebAuthn) 서명을 필수로 하며, 사용자에게 **사람이 읽을 수 있는 요약**을 보여주고 그 요약의 해시를 Mandate에 포함한다.
- **FR-MD-3** Mandate는 특정 에이전트(운영사 + 선택적으로 인스턴스) 에 바인딩된다.
- **FR-MD-4** 사용자는 지갑(웹/앱)에서 Mandate 목록, 사용 내역, 잔여 한도를 보고 즉시 철회할 수 있다.
- **FR-MD-5** 재위임(sub-delegation)은 원 Mandate가 허용한 경우에만, 원 범위의 **부분집합**으로만 가능하다(범위 축소 원칙, attenuation).
- **FR-MD-6** 반복(구독형) Mandate와 1회성(Cart 확정형) Mandate 모두 지원.

### 3.3 거래 시점 검증
- **FR-TX-1** 에이전트는 거래 직전 Mandate를 **Transaction Token**(단명, 5분, 1회용, 특정 머천트·금액에 고정)으로 교환한다.
- **FR-TX-2** 교환 시 AgentPass는 누적 한도·빈도·위험 점수를 평가해 `allow` / `step_up` / `deny` 를 반환한다.
- **FR-TX-3** 머천트는 SDK로 (a) HTTP 서명, (b) Transaction Token 서명·만료·audience, (c) 토큰-요청키 바인딩, (d) 장바구니 해시 일치, (e) 철회 상태를 검증한다. (a)~(d)는 오프라인 검증 가능.
- **FR-TX-4** 머천트는 거래 완료 후 결과(승인/실패, 최종 금액)를 AgentPass에 보고(capture)해 누적 한도를 정산한다.
- **FR-TX-5** Step-up 시 사용자에게 CIBA 푸시 → 패스키 승인 → 에이전트는 폴링/콜백으로 결과 수신.

### 3.4 결제 자격증명 중개
- **FR-PAY-1** AgentPass는 카드번호(PAN)를 저장하지 않는다. PSP/네트워크 토큰 참조만 보관한다.
- **FR-PAY-2** 승인된 Transaction Token에 대해 PSP별 **1회용·금액 제한 결제 자격증명**(예: Shared Payment Token, Agentic Token)을 발급 요청해 머천트에 전달한다.

### 3.5 감사·증빙
- **FR-AU-1** Mandate 발급, 토큰 교환, Step-up, capture, 철회 이벤트는 해시 체인 영수증으로 기록한다.
- **FR-AU-2** 거래별 **Evidence Bundle**(Mandate + 사용자 승인 서명 + Transaction Token + 장바구니 + 에이전트 요청 서명 + 영수증 체인 증명)을 머천트·PSP가 조회하고 **제3자가 독립 검증** 가능해야 한다.

### 3.6 개발자 경험
- **FR-DX-1** Agent SDK(TypeScript, Python): 키 관리, 요청 서명, 토큰 교환, MCP 툴 래퍼.
- **FR-DX-2** Merchant SDK(TypeScript, Python, Java, Go): 검증 미들웨어 (Express / FastAPI / Spring / net/http).
- **FR-DX-3** CDN/WAF 플러그인(Cloudflare Workers, AWS CloudFront Functions)으로 에지 검증.
- **FR-DX-4** 샌드박스 환경과 테스트 Mandate 생성기.

## 4. 비기능 요구사항 (NFR)

| ID | 항목 | 목표 |
|---|---|---|
| NFR-1 | 검증 지연 (오프라인 SDK) | p99 ≤ 2ms |
| NFR-2 | 토큰 교환 API 지연 | p99 ≤ 50ms (리전 내) |
| NFR-3 | 가용성 | 토큰 교환 99.99%, 지갑 99.9% |
| NFR-4 | 철회 전파 | p99 ≤ 60초 (Status List), Webhook 구독 시 ≤ 5초 |
| NFR-5 | 처리량 | 초당 토큰 교환 10,000건 (v1 GA) |
| NFR-6 | 보안 | 서명 키 HSM/KMS 보관, 모든 토큰 송신자 제약, OWASP ASVS L2 |
| NFR-7 | 개인정보 | 머천트에 최소 정보 공개(SD-JWT), 데이터 보존 기간 정책, 국내 개인정보보호법·GDPR 준수 |
| NFR-8 | 규제 | 전자금융거래법상 접근매체 관리 요건, PSD2/3 SCA 위임 증빙과 매핑 가능 |
| NFR-9 | 감사 | 영수증 체인 무결성 외부 검증 가능, 7년 보관 옵션 |
| NFR-10 | 상호운용 | AP2 Mandate(VC) ↔ AgentPass Mandate 변환, Web Bot Auth 서명 호환 |

## 5. 위험 등급 정책 (기본값, 사용자/머천트가 강화 가능)

| 등급 | 조건 예 | 동작 |
|---|---|---|
| Low | Mandate 범위 내, 1회 금액 ≤ 한도의 50%, 기존 거래 머천트 | 자동 승인 |
| Medium | 신규 머천트, 한도 50~100%, 비정상 시간대 | 자동 승인 + 사용자 알림 |
| High | 한도 초과, 배송지 변경, 운영사 신뢰등급 `registered`, 위험 점수 ≥ 0.7 | Step-up(패스키) 필수 |
| Critical | 폐기된 키, 철회 Mandate, 서명 불일치, replay | 거부 + 보안 이벤트 |

## 6. 성공 지표

- 머천트: 에이전트 경유 전환율, 에이전트 관련 차지백 비율(목표: 일반 CNP 대비 ≤ 50%)
- 사용자: Mandate 발급 완료율, 철회 후 미승인 거래 0건
- 운영사: SDK 연동 소요 시간(목표 ≤ 1일)

## 7. 범위 외 (v1)

- 스테이블코인/x402 결제 레일 (v2 후보)
- 에이전트 간 협상(A2A) 프로토콜 자체 구현
- 오프라인(매장) 결제
