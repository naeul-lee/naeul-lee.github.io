# AgentPass 프로토타입

`docs/04-protocol/protocol-spec.md`가 실제로 동작하고 위협 모델의 대응책이 유효한지 확인하려고 만든 **설계 검증용 레퍼런스 구현**입니다. 서버, 네트워크, DB 없이 메모리 안에서 모든 참여자를 시뮬레이션합니다.

## 실행

```bash
pip install cryptography        # 유일한 의존성
cd prototype
python3 demo.py                 # 해설이 붙은 엔드-투-엔드 시나리오
python3 -m unittest discover -s tests -t .   # 테스트 39개
```

## 구성

| 모듈 | 내용 | 대응 명세 |
|---|---|---|
| `agentpass/crypto.py` | Ed25519, JWK 썸프린트(RFC 7638), compact JWS, `typ` 강제 | §0 |
| `agentpass/httpsig.py` | RFC 9421 서명/검증(AgentPass 프로파일), Content-Digest | §1.3 |
| `agentpass/policy.py` | constraints 평가, 위험 등급, 범위 축소(attenuation) 검사, 동의 문구 생성 | §2.3, PRD §5 |
| `agentpass/server.py` | Registry, Mandate, Token Exchange, Step-up, Capture, 철회, 재위임, 증빙 | §1–§5 |
| `agentpass/agent.py` | Agent SDK: Instance Assertion, DPoP 증명, 요청 서명 | §1.1, §3.1 |
| `agentpass/merchant.py` | Merchant SDK: 오프라인 검증 9단계 | §3.3 |
| `agentpass/ledger.py` | 해시 체인 + 서명 체크포인트, 독립 검증 | §5 |

## 검증된 시나리오 (M2 완료 기준)

| 시나리오 | 테스트 |
|---|---|
| 정상 위임 구매 | `test_happy_path_purchase` |
| 한도 초과 → Step-up | `test_stepup_required_then_approved`, `test_stepup_approval_cannot_be_reused_for_other_cart` |
| 철회된 Mandate 거부 | `test_revoked_mandate_rejected` |
| 다른 에이전트 키로 토큰 재사용 거부 | `test_stolen_token_other_agent_rejected`, `test_mandate_unusable_by_other_operator` |
| 요청 본문 변조 거부 | `test_tampered_body_rejected`, `test_tampered_path_rejected` |
| 재전송 거부 | `test_replay_rejected`, `test_dpop_proof_replay_rejected` |
| 영수증 체인 변조 탐지 | `test_ledger_tamper_detected` |

추가로 누적 한도, 미확정 예약분 반영, 예약 만료, 머천트·카테고리·행위 제약, 재위임 범위 축소·깊이 제한·연쇄 철회, 인스턴스 폐기, 수명 상한, 운영사 등급 정책, audience, 토큰 타입 혼동, Status List 갱신 지연 시 fail-closed, pairwise 가명 ID까지 테스트합니다.

## 의도적으로 단순화한 부분 (프로덕션과 다름)

- **WebAuthn**: 사용자 패스키를 Ed25519 서명으로 흉내 냄. authenticatorData와 clientDataJSON 검증은 생략.
- **JCS**: `json.dumps(sort_keys=True)`로 근사. 정수와 문자열만 쓰는 페이로드에서는 RFC 8785와 결과가 같음.
- **RFC 9421**: 서명 라벨 하나(`ap`), Structured Fields 파서는 최소한만 구현.
- **Status List**: 비트맵 대신 철회된 ID 집합 스냅샷을 씀.
- **한도 카운터**: 단일 프로세스 메모리. 프로덕션에서는 Redis Lua로 check-and-reserve를 원자적으로 처리.
- **Evidence Bundle**: 원장 전체를 반환함. 프로덕션에서는 해당 거래 엔트리부터 체크포인트까지의 **포함 증명만** 반환해 다른 사용자 이벤트가 노출되지 않게 해야 함.
- **SD-JWT 선택적 공개, PSP 어댑터, CIBA 푸시 전송**은 구현하지 않음(인터페이스 자리만 있음).
