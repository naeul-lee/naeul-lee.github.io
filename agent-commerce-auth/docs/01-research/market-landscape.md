# 시장 · 경쟁 환경 조사 (Agentic Commerce)

> 조사 기준일: 2026-10-14. 2차 자료(블로그·인터뷰)가 다수 포함되어 있으므로, 파일럿 착수 전 각 사의 공식 문서로 재검증 필요.

## 1. 흐름 요약

- 2025년 하반기부터 카드 네트워크·빅테크가 "에이전트 결제"용 프로토콜을 연이어 발표했다.
- 업계는 이들을 **경쟁자라기보다 계층(layer)** 으로 본다.
  - Foundation: MCP(도구 연결), A2A(에이전트 간 통신)
  - Commerce: ACP, UCP(상품 탐색·체크아웃)
  - Payment: AP2, 카드 네트워크 프로그램(Visa / Mastercard), x402(스테이블코인·HTTP 402)
- 2026년 4월 기준 MCP·A2A·AP2·UCP가 Linux Foundation 산하로 이관되었다는 보도가 있음(2차 자료).
- 소비자 수용도는 아직 낮음: 2026년 초 기준 완전 자율 구매를 허용하는 소비자는 약 4% 수준이라는 추정(2차 자료) → **신뢰·통제 수단이 수용의 병목**이라는 우리의 가설을 지지.

## 2. 주요 플레이어

| 이니셔티브 | 주체 | 핵심 개념 | 우리와의 관계 |
|---|---|---|---|
| **AP2** (Agent Payments Protocol) | Google 주도, 다수 참여 | Intent / Cart / Payment **Mandate** 를 서명된 VC로 전달 | Mandate 개념을 차용, **AP2 Mandate 발급자(Issuer)·검증자**로 동작 가능하게 매핑 |
| **ACP** (Agentic Commerce Protocol) | OpenAI · Stripe | 에이전트 체크아웃, Shared Payment Token | 체크아웃 흐름에 AgentPass 검증 헤더를 얹는 어댑터 |
| **Visa Trusted Agent Protocol / Intelligent Commerce** | Visa (Cloudflare 협력) | 에이전트 신원 + 소비자 인가를 동시에 검증, HTTP 서명 기반 | 동일하게 RFC 9421 서명 사용 → 호환 프로파일 |
| **Mastercard Agent Pay** | Mastercard | Know Your Agent 등록, **Agentic Token**, Verifiable Intent | KYA 등록 정보 연동, 네트워크 토큰을 결제 수단으로 중개 |
| **Web Bot Auth** | Cloudflare 등, IETF 논의 | 봇 요청을 HTTP Message Signatures 로 서명, 공개키 디렉토리 | 에이전트 요청 인증 계층을 그대로 준수 |
| **x402** | Coinbase 등 | HTTP 402 기반 마이크로결제 | v2 이후 결제 레일 어댑터 후보 |
| **에이전트 신원/인가 스타트업** | Skyfire(KYAPay), 각종 IdP(Okta/Auth0, WorkOS 등) | 에이전트 ID, 에이전트용 OAuth | 직접 경쟁. 차별점은 아래 §3 |

## 3. 시장 공백 (우리의 기회)

1. **네트워크 중립 검증 계층**: 머천트는 Visa·Mastercard·AP2·ACP를 각각 연동하고 싶지 않다. "한 번 연동하면 모든 에이전트 프로토콜을 검증"하는 **머천트 측 단일 검증기**가 비어 있다.
2. **결제 이외의 인증**: 기존 프로그램은 결제 순간에 집중. 실제 커머스는 로그인, 장바구니, 주문조회, 반품/교환, 멤버십 포인트 사용 등 **계정 행위** 전체에 에이전트 인가가 필요하다.
3. **사용자 통제 UX**: 위임 한도 설정·실시간 철회·사용 내역을 한 곳에서 보는 **사용자용 위임 지갑(Consent Wallet)** 이 표준화되어 있지 않다.
4. **분쟁 증빙 표준**: "에이전트가 내 의도와 다르게 샀다" 분쟁에 쓸 수 있는, 머천트·PSP·이슈어가 모두 검증 가능한 증빙 번들이 부족하다.
5. **지역 시장(한국)**: PG 중심 구조, 간편결제 사업자, 본인확인 제도 등 로컬 특성에 맞춘 어댑터가 글로벌 플레이어에게 후순위다.

## 4. 포지셔닝

> **"에이전트를 위한 Stripe Radar + Okta"** — 머천트에게는 에이전트 신원·위임 검증과 위험 점수를,
> 사용자에게는 안전한 위임 지갑을, 에이전트 운영사에게는 표준 SDK를 제공하는 **중립 신뢰 계층**.

- 경쟁하지 않는다: 카드 네트워크·AP2 위에 **어댑터**로 붙는다.
- 차별화: (1) 다중 프로토콜 단일 검증, (2) 결제 외 계정 행위까지 커버, (3) 증빙 체인.

## 5. 비즈니스 모델 (가설)

| 고객 | 과금 |
|---|---|
| 머천트 | 검증 API 호출당 과금 (월 N회 무료), 차지백 보호 옵션 |
| 에이전트 운영사 | 등록·KYA 인증 연회비, 고신뢰 등급(Verified) 배지 |
| 사용자 | 무료 (지갑은 운영사·머천트 비용으로 운영) |

## 참고 자료

- AP2 해설: https://eco.com/support/en/articles/15192002-ap2-protocol-explained-google-s-agentic-commerce-standard-2026
- 프로토콜 비교(2026): https://atxp.ai/blog/mastercard-agent-pay-stripe-acp-visa-x402-comparison-2026
- MCP vs A2A vs AP2: https://stellagent.ai/insights/mcp-vs-a2a-vs-ap2-protocol-comparison
- Visa TAP 용어집: https://www.paz.ai/glossary/visa-trusted-agent-protocol
- ACP 용어집: https://www.paz.ai/glossary/agentic-commerce-protocol-acp
- Mastercard Agent Pay: https://www.mastercard.com/fi/fi/business/teko%C3%A4ly/mastercard-agent-pay.html
- Mastercard × Checkout.com 인터뷰: https://www.checkout.com/es-es/blog/mastercard-x-checkout-una-conversacion-sobre-el-agentic-commerce
- Mastercard 파일럿(독일, 2026-06): https://www.it-finanzmagazin.de/mastercard-pilot-agent-pay-ohne-issuer-umbau-bei-deutsche-bank-dz-bank-und-n26-246419/
