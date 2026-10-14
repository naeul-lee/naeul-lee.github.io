# ADR-0005: 위험 등급 기반 Step-up (Passkey / CIBA)

- 상태: Accepted · 2026-10-14

## Context
모든 거래에 사용자 확인을 요구하면 에이전트의 가치가 사라지고, 전혀 요구하지 않으면 사기·오작동 피해가 커진다.

## Decision
Token Exchange 시 Policy Engine이 `low/medium/high/critical` 등급을 산출(PRD §5). `high`는 CIBA 푸시 + **패스키 서명**으로 Step-up. 승인 challenge는 `hash(binding_message ‖ cart_hash)`로, 사용자가 본 금액·머천트에 서명하도록 한다. 승인 결과는 Tx Token `amr`에 `stepup_webauthn`으로 표기.

## Alternatives
- SMS OTP: 피싱·SIM 스와핑 취약, 무엇을 승인했는지 바인딩 불가.
- 항상 Step-up: UX 실패.

## Consequences
- (+) 머천트·이슈어에 "사용자 실재 승인" 신호 제공 → SCA 위임 증빙 및 책임 전가(liability shift) 협상 근거.
- (−) Step-up 피로 공격 대응 필요 (rate limit, 연속 거절 시 Mandate 정지).
