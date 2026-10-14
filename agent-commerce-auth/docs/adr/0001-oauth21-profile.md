# ADR-0001: 신규 프로토콜 대신 OAuth 2.1 확장 프로파일

- 상태: Accepted · 2026-10-14

## Context
에이전트 위임은 본질적으로 "사용자가 제3자 클라이언트에 제한된 권한을 위임"하는 문제로, OAuth가 해결해 온 문제의 연장이다. MCP 인가 스펙이 OAuth 2.1을 채택했고, IETF의 에이전트 관련 초안 다수(draft-liu-…, draft-mishra-…)도 새 메커니즘 없이 기존 확장을 조합하는 방향이다.

## Decision
OAuth 2.1 위에 RAR(RFC 9396), Token Exchange(RFC 8693), DPoP(RFC 9449), PAR(RFC 9126), CIBA를 조합한 **AgentPass 프로파일**을 정의한다. 새로 정의하는 것은 `authorization_details` 타입, 토큰 `typ`, 몇 개의 클레임(`constraints`, `cart_hash`, `consent`)뿐이다.

## Alternatives
- **GNAP**: 위임 표현력은 더 좋지만 라이브러리·운영 경험 부족, MCP와 불일치.
- **완전 자체 프로토콜**: 빠르지만 머천트·IdP 생태계가 따라오지 않음.
- **AP2만 채택**: 결제 계층에 집중되어 있어 로그인·주문조회 등 계정 행위 위임을 덮지 못함 → 어댑터로 지원.

## Consequences
- (+) 기존 OAuth 라이브러리·IdP 재사용, 보안 분석 자산 활용.
- (+) IETF 표준화 진행 시 따라가기 쉬움.
- (−) OAuth 확장 다수 조합의 복잡도 → SDK가 감춰야 함.
