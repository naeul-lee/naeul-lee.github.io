# AgentPass — AI 에이전트 커머스를 위한 인증·위임 인프라

AI 에이전트가 사용자를 대신해 상품을 찾고, 주문하고, 반품까지 하는 시대에 머천트는 세 가지를 확인해야 합니다.

1. **누가** 보냈나? → **Agent Identity**: 등록된 운영사와 인스턴스, RFC 9421 요청 서명
2. **누구를 대신해, 무엇을 해도 되나?** → **Mandate**: 사용자가 패스키로 서명한, 한도가 정해진 위임
3. **이번 거래가 그 범위 안인가?** → **Transaction Token**: 이 장바구니, 이 금액, 이 머천트, 이 에이전트 키에 고정된 5분짜리 1회용 토큰

AgentPass는 이 세 가지를 **OAuth 2.1 확장 프로파일**로 제공합니다. 머천트는 SDK로 오프라인 검증만 하면 되고, 사용자는 지갑에서 언제든 위임을 철회할 수 있습니다. 거래 이력은 제3자가 검증할 수 있는 해시 체인으로 남습니다.

## 문서 읽는 순서

| 단계 | 문서 | 내용 |
|---|---|---|
| 계획 | [docs/00-plan/project-plan.md](docs/00-plan/project-plan.md) | 문제 정의, 목표, 단계, 마일스톤, 리스크, 결정 요약 |
| 리서치 | [docs/01-research/market-landscape.md](docs/01-research/market-landscape.md) | AP2, ACP, Visa TAP, Mastercard Agent Pay와 시장 공백 |
| | [docs/01-research/standards-survey.md](docs/01-research/standards-survey.md) | 채택한 표준, IETF 에이전트 초안, 채택하지 않은 기술 |
| 요구사항 | [docs/02-requirements/prd.md](docs/02-requirements/prd.md) | 페르소나, 유스케이스 10개, 기능·비기능 요구사항, 위험 등급 정책 |
| 아키텍처 | [docs/03-architecture/system-architecture.md](docs/03-architecture/system-architecture.md) | 신뢰 모델, 컴포넌트, 배포, 장애 시 동작 |
| | [docs/03-architecture/sequence-diagrams.md](docs/03-architecture/sequence-diagrams.md) | 등록, 위임, 자동 구매, Step-up, 철회, 재위임 |
| | [docs/03-architecture/data-model.md](docs/03-architecture/data-model.md) | ERD, 테이블 정의 |
| | [docs/03-architecture/threat-model.md](docs/03-architecture/threat-model.md) | STRIDE와 에이전트 특화 위협 18개, 대응책, 테스트 매핑 |
| 프로토콜 | [docs/04-protocol/protocol-spec.md](docs/04-protocol/protocol-spec.md) | 토큰 형식, 서명 프로파일, 검증 절차, 외부 프로토콜 매핑 |
| API | [docs/05-api/openapi.yaml](docs/05-api/openapi.yaml) | OpenAPI 3.1 |
| 결정 기록 | [docs/adr/](docs/adr/README.md) | ADR 9건 |
| 프로토타입 | [prototype/](prototype/README.md) | Python 레퍼런스 구현과 테스트 39개 |

## 빠른 실행

```bash
pip install cryptography
cd prototype && python3 demo.py && python3 -m unittest discover -s tests -t .
```

## 상태

- [x] P0 리서치 · P1 요구사항 · P2 아키텍처 · P3 프로토콜 · P4 API · P5 프로토타입
- [ ] ADR-0008 인가 서버 구현 방식 스파이크 (Ory Hydra 확장 vs 자체 구현)
- [ ] 프로토콜 테스트 벡터(JSON) 추출. Go 구현과 공유하는 용도
- [ ] P6 파일럿: 머천트 2곳, 에이전트 운영사 2곳

## 저장소에 대해

이 디렉토리는 외부 파일에 의존하지 않는 독립 프로젝트입니다. 새 저장소로 분리하는 방법은 [ADR-0009](docs/adr/0009-repository-layout.md)를 참고하세요.
