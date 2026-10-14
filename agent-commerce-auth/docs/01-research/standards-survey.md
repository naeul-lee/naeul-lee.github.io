# 표준 기술 조사

> 목적: "새로 발명하지 않는다." 검증된 표준을 조합(profile)해 AgentPass를 구성한다.
> 업계 IETF 초안들도 대부분 "새 메커니즘 없이 기존 OAuth/JOSE 확장을 프로파일링"하는 방향으로 수렴 중이다.

## 1. 채택 표준

| 표준 | 용도 | AgentPass에서의 사용 |
|---|---|---|
| **OAuth 2.1** (draft-ietf-oauth-v2-1) | 인가 프레임워크 | 전체 인가 서버의 기반. PKCE 필수, implicit 제거 |
| **RFC 9396** Rich Authorization Requests (RAR) | 구조화된 권한 요청 | `authorization_details.type = "agentpass_mandate"` 로 금액·머천트·카테고리 한도 표현 |
| **RFC 8693** Token Exchange | 위임 토큰 교환, `act` 클레임 | Mandate → 거래별 단명 Access Token 교환, `act`로 에이전트 체인 표현 |
| **RFC 9449** DPoP / **RFC 7800** `cnf` | 송신자 제약 토큰 | 토큰을 에이전트 인스턴스 키에 바인딩 → 탈취 토큰 무용화 |
| **RFC 9421** HTTP Message Signatures | 요청 무결성·출처 인증 | 에이전트의 모든 머천트 요청 서명 (Web Bot Auth 호환) |
| **RFC 7591** Dynamic Client Registration | 에이전트 등록 | 에이전트 인스턴스 자동 등록 |
| **OpenID CIBA** | 분리 채널 사용자 승인 | 사용자 부재 시 휴대폰 푸시로 Step-up |
| **WebAuthn / Passkeys** | 피싱 저항 사용자 인증 | Mandate 발급·Step-up 승인 서명 |
| **SD-JWT** / SD-JWT VC (IETF OAuth WG) | 선택적 공개 | 사용자 개인정보(배송지 등)를 머천트가 필요한 만큼만 공개 |
| **IETF Token Status List** (draft-ietf-oauth-status-list) | 대규모 철회 상태 | Mandate 철회 상태를 비트맵으로 배포 |
| **RFC 7517** JWKS / **RFC 8037** EdDSA | 키 배포·서명 알고리즘 | 기본 알고리즘 Ed25519, 대체 ES256 |
| **W3C VC Data Model 2.0** | 자격증명 상호운용 | AP2 Mandate(VC) 와의 변환 어댑터 |

## 2. 관련 IETF 초안 (참고, 추적 대상)

| 초안 | 요지 | 시사점 |
|---|---|---|
| draft-oauth-ai-agents-on-behalf-of-user | 인가 요청에 에이전트 식별 파라미터, 토큰 요청에 agent token 추가 | 우리 `agent_id` 파라미터 설계와 정합 |
| draft-liu-ai-agent-authorization-integration | 새 메커니즘 없이 기존 OAuth 확장 조합 (Okta 등 참여) | ADR-0001 방향성 지지 |
| draft-mishra-oauth-agent-grants | 에이전트 클라이언트 식별, 동의, 송신자 제약, 토큰 교환 프로파일 | 거의 동일한 구성 — 호환성 유지 대상 |
| draft-mcguinness-oauth-ai-agent-instance | 하나의 client_id 아래 다수 에이전트 **인스턴스** | Operator / Instance 2단 신원 모델(ADR-0003)과 정합 |
| draft-klrc-aiagent-auth | 기존 메커니즘 재사용 권고 | 동일 |
| draft-yao-agent-auth-considerations | 에이전트 통신망용 OAuth 확장 고려사항 | 참고 |

## 3. 검토 후 미채택

| 기술 | 미채택 사유 |
|---|---|
| GNAP (RFC 9635) | 설계는 우수하나 생태계·라이브러리 부족, MCP가 OAuth 2.1을 채택 |
| mTLS 단독 | CDN 뒤에서 종단 간 유지 어려움, 브라우저형 에이전트에 부적합 → HTTP 서명으로 대체 (mTLS는 서버 간 선택 옵션) |
| 블록체인 기반 DID 레지스트리 | 지연·비용·규제 불확실. `did:web` 수준의 HTTPS 기반 키 디렉토리로 충분 |
| API Key 방식 | 사용자 위임 표현 불가, 유출 시 피해 범위 큼 |

## 참고 자료

- WorkOS, OAuth on behalf of AI agents: https://workos.com/blog/oauth-on-behalf-of-ai-agents
- draft-oauth-ai-agents-on-behalf-of-user-02: https://www.ietf.org/archive/id/draft-oauth-ai-agents-on-behalf-of-user-02.txt
- draft-klrc-aiagent-auth-03: https://www.ietf.org/archive/id/draft-klrc-aiagent-auth-03.xml
- draft-mcguinness-oauth-ai-agent-instance-00: https://datatracker.ietf.org/doc/draft-mcguinness-oauth-ai-agent-instance/00/
- draft-yao-agent-auth-considerations-01: https://www.ietf.org/archive/id/draft-yao-agent-auth-considerations-01.html
- draft-mishra-oauth-agent-grants-02: https://apache.otenet.gr/doc/internet-drafts/draft-mishra-oauth-agent-grants-02.html
- draft-liu-ai-agent-authorization-integration-00: https://ftp.sparcs.org/ietf/draft-liu-ai-agent-authorization-integration-00.html
- 해설: https://techstackups.com/articles/authenticating-ai-agents-ietf-draft/
