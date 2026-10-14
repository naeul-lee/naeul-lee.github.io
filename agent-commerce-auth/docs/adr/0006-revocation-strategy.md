# ADR-0006: 단명 토큰 + Status List + Webhook 철회

- 상태: Accepted · 2026-10-14

## Context
"즉시 철회"와 "머천트 오프라인 검증"은 상충한다.

## Decision
3중 구조:
1. **교환 시점 실시간 확인** — Mandate가 철회되면 Tx Token 발급 자체가 즉시 중단(가장 중요한 방어선).
2. **Tx Token 5분 수명** — 이미 발급된 토큰의 최대 노출 시간 제한. 철회 시 미사용 `jti`는 블록리스트로 Webhook 전파.
3. **Token Status List** (30초 갱신, 60초 TTL) + **Webhook** (≤5초) — 머천트 측 반영.

## Alternatives
- 매 요청 introspection: 가용성 종속, 지연.
- CRL 형 전체 목록: 규모 증가 시 비효율 → 비트맵 Status List.

## Consequences
- (+) 철회 후 신규 거래 0건 보장(교환 차단), 기존 토큰 노출 ≤ 5분.
- (−) Status List 갱신 지연 시 fail-closed 정책 필요 (`max_staleness`).
