# ADR-0003: Mandate 형식과 2단 신원·키 바인딩

- 상태: Accepted · 2026-10-14

## Context
Mandate는 (1) 오프라인 검증 가능, (2) 탈취돼도 무용, (3) 머천트에 최소 정보만 노출, (4) AP2의 VC Mandate와 상호 변환 가능해야 한다. 에이전트는 수평 확장되므로 하나의 운영사 아래 수천 개 인스턴스가 뜬다.

## Decision
- 형식: **AgentPass 서명 JWT** (`typ: agentpass-mandate+jwt`). 증빙 번들에서 머천트에 공개할 때는 **SD-JWT** 로 constraints 일부만 선택 공개.
- 신원 2단: **Operator(장기, KYB)** → **Instance(≤24h 키)**. Mandate는 기본적으로 Operator에 바인딩(`azp`), 선택적으로 특정 인스턴스(`cnf.jkt`). 
- Mandate는 머천트에 직접 제시하지 않는다. 머천트는 항상 거래별 Tx Token(인스턴스 키 바인딩)만 받는다.

## Alternatives
- Mandate를 인스턴스 키에 직접 바인딩: 인스턴스 재기동마다 사용자 재동의 필요 → UX 붕괴.
- W3C VC(JSON-LD) 원형: 정규화 복잡도·라이브러리 부담. 어댑터로 변환 제공.
- 불투명(opaque) 토큰 + 매번 introspection: 머천트 핫패스가 AgentPass 가용성에 종속.

## Consequences
- (+) 인스턴스 키 유출 피해 = 최대 24시간·해당 인스턴스 한정.
- (+) 사용자 한도 정보가 머천트에 새지 않음.
- (−) 토큰 교환 왕복 1회 추가(목표 p99 50ms).
