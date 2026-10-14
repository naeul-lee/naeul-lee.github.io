# ADR-0004: 카드번호 미보관, 결제 자격증명 중개

- 상태: Accepted · 2026-10-14

## Context
PAN을 보관하면 PCI DSS Level 1 범위에 전면 진입하고, 국내에서는 전자금융업 등록 이슈가 커진다. 카드 네트워크는 이미 에이전트용 토큰(Agentic Token 등)을, PSP는 Shared Payment Token 같은 범위 제한 토큰을 제공한다.

## Decision
AgentPass는 **PSP/네트워크 토큰 참조만** 보관하는 Payment Credential Broker를 둔다. Tx Token 승인 시 PSP 어댑터를 통해 **1회용·금액 상한·머천트 고정** 결제 자격증명을 발급받아 에이전트에 전달한다. 결제 승인·정산은 머천트-PSP 간 기존 경로 그대로.

## Alternatives
- 자체 가상카드 발급: 수익성은 있으나 라이선스·자본 요건 과다 (v3 이후 검토).
- 결제 무관(인증만): 머천트 가치가 반감 — 결제 자격증명 범위를 Mandate에 맞추는 것이 핵심 가치.

## Consequences
- (+) 규제·보안 범위 최소화, 기존 결제 인프라 재사용.
- (−) PSP별 어댑터 유지 비용. 초기 지원: Stripe, Visa/Mastercard 에이전트 프로그램, 국내 PG 1~2곳 빌링키.
