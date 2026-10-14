# ADR-0002: 에이전트 요청 인증에 RFC 9421 HTTP Message Signatures

- 상태: Accepted · 2026-10-14

## Context
머천트는 "이 요청이 정말 등록된 에이전트에서 왔는가"를 CDN/WAF 단에서, 본문 무결성까지 포함해 확인하고 싶다. Visa TAP·Cloudflare Web Bot Auth가 RFC 9421 기반으로 수렴 중이다.

## Decision
모든 에이전트 요청은 RFC 9421로 서명하며, `Signature-Agent` 헤더로 키 디렉토리를 가리킨다(Web Bot Auth 호환). 구매 계열 요청은 `content-digest`와 `agentpass-transaction` 헤더를 서명 대상에 MUST 포함한다. `keyid`는 인스턴스 키 `jkt` — Tx Token의 `cnf.jkt`와 같은 값이므로 **서명 하나로 신원 확인과 토큰 바인딩을 동시에** 해결한다.

## Alternatives
- **mTLS**: CDN에서 종료되어 오리진까지 신원이 전달되지 않음, 브라우저형 에이전트에 부적합.
- **DPoP만 사용**: DPoP는 AS/RS 대상 토큰 바인딩용이며 본문 무결성을 보장하지 않음. → AgentPass 토큰 엔드포인트에는 DPoP, 머천트 요청에는 RFC 9421로 역할 분리.
- **API Key/Bearer**: 탈취 시 재사용 가능.

## Consequences
- (+) 에지 검증 가능, 업계 호환.
- (−) 머천트가 서명 베이스 재구성 시 프록시가 헤더를 바꾸면 실패 → 서명 대상 컴포넌트를 최소로 고정하고 SDK 제공.
