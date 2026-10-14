# ADR-0009: 저장소 구성

- 상태: Accepted · 2026-10-14

## Context
요청은 "신규 git repo에서 작업"이었으나, 작업 환경의 GitHub 통합이 저장소 생성 권한을 갖고 있지 않았다(`POST /user/repos → 403 Resource not accessible by integration`).

## Decision
기존 저장소의 작업 브랜치에 **완전히 독립된 최상위 디렉토리 `agent-commerce-auth/`** 로 시작한다. 디렉토리 밖 파일에 의존하지 않으므로 언제든 다음으로 새 저장소로 분리할 수 있다.

```bash
git subtree split --prefix=agent-commerce-auth -b agentpass-only
git push git@github.com:<owner>/agent-commerce-auth.git agentpass-only:main
```

## Consequences
- (+) 이력 보존한 채 분리 가능.
- (−) 기존 저장소가 GitHub Pages(Jekyll)라서 main에 병합 시 문서가 사이트에 노출될 수 있음 → 분리 전 main 병합 금지, 필요하면 `_config.yml`의 `exclude`에 추가.
