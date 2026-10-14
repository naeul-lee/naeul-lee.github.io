# ADR-0008: 기술 스택

- 상태: Accepted · 2026-10-14

## Decision
| 영역 | 선택 | 이유 |
|---|---|---|
| 코어 서비스 | **Go** | 낮은 지연, 단일 바이너리, 성숙한 JOSE/암호 라이브러리 |
| 인가 서버 | **Ory Hydra(OSS) 기반 확장 PoC 후 결정**, 기본안은 자체 구현(Go) | RAR·Token Exchange·CIBA 커스터마이징 폭이 커서 자체 구현 가능성 높음. 파일럿 전 2주 스파이크로 확정 |
| SDK | TypeScript, Python (Agent / Merchant), Java·Go (Merchant) | 에이전트 생태계(TS/Python), 머천트 백엔드(Java/Go) |
| DB | PostgreSQL 16 | 트랜잭션·JSONB·파티셔닝 |
| 캐시/카운터 | Redis Cluster (Lua 원자 연산) | 한도 check-and-reserve |
| 키 관리 | Cloud KMS / HSM (Ed25519 지원 확인, 미지원 시 ES256) | 키 비노출 서명 |
| 이벤트 | Kafka (또는 관리형) | Webhook·Status List·Ledger 비동기 파이프라인 |
| 배포 | Kubernetes, 멀티 리전(KR 우선) | 데이터 거주성 |
| 프로토타입 | Python 3.13 + `cryptography` | 설계 검증 속도 |

## Consequences
- 프로토타입(Python)과 프로덕션(Go)의 언어가 다르므로, **프로토콜 테스트 벡터**(JSON)를 공유 자산으로 만들어 구현 간 일치를 보장한다.
