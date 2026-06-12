# RBAC 접근 매트릭스 정정 + 비로그인 환자패널 버그 수정 — 설계

**Goal:** 계정 레벨(patient/staff/admin)별 페이지 접근 매트릭스를 의도대로 정정하고, 비로그인 시
로그인 페이지가 강제되는 결함을 고쳐 환자용 패널이 렌더되게 한다. 회진 모드를 의료진(staff) 이상에 개방.

**Architecture:** 페이지 RBAC는 프론트 `middleware.ts` + 순수표 `lib/auth.ts`, API RBAC는 백엔드
`auth.py`(`before_request`). 두 표를 정합시키고, 홈 `/`을 역할적응 렌더로 바꾼다.

---

## 정정 매트릭스

| 라우트 | 최소등급(정정) | 비고 |
| --- | --- | --- |
| `/` 홈 | patient | 역할적응: 환자=문진 안내패널 / staff·admin=대시보드(회진 포함) |
| `/intake` | patient | |
| `/display` | patient | 키오스크(QR→문진 유도) |
| `/qr` | staff | 스캔 스테이션 |
| `/ocr` · `/patients` | staff | |
| `/console` · `/debug` | admin | |
| 회진 모드(홈 내) | staff+ | 환자에겐 미노출 |

## 발견된 결함(감사 결과)

1. **비로그인 → /login 강제**: patient가 `/`(admin필요) 접근 시 미들웨어가 `landingFor` 무시하고 `/login`.
2. **회진이 admin 전용 홈**: staff가 홈 접근 불가 → 회진 시작 불가(요구 상충).
3. **`/map` 깨진 링크**: 홈 배너가 존재하지 않는 `/map`으로 이동.
4. **`/display`·`/qr` admin 전용**(catch-all): 키오스크/스캔 용도와 불일치.
5. **`landingFor(patient)=/intake` 인데 미들웨어는 /login** — 자기모순.

## 변경 사항

### 1. `lib/auth.ts`
- `requiredRoleForRoute`: `/`·`/intake`·`/display` → patient; `/patients`·`/ocr`·`/qr` → staff; 그 외 admin.
- `landingFor`: 모든 역할 `/`(역할적응 홈이 허브).
- `NAV_ROLES`: `"/"`→patient, `"/qr"`→staff 추가(사이드바 노출 정정).

### 2. `middleware.ts`
- 권한부족 분기에서 patient의 `/login` 강제 제거 → **항상 `landingFor(role)`로 리다이렉트**.

### 3. `app/page.tsx` (홈 역할적응)
- `getMe()`로 role 취득(Sidebar와 동일).
- `role === "patient"` → **환자 패널**(환영 + "문진 시작" → `/intake`) 렌더, 회진·대시보드 미노출.
- staff·admin → 기존 대시보드. 배너에 `minRole` 부여 후 `roleAtLeast`로 필터:
  - 관제 배너 `href` `/map` → **`/console`**(admin), 환자정보 staff, 문진 patient, 디버그 admin.
- 회진 모드 블록은 staff+ 분기에서만 렌더(환자 분기는 early return).

### 4. `backend/auth.py`
- `required_role_for_path`: `/api/display` 프리픽스 → patient(키오스크 read). 나머지 동일.

## 검증
- `backend/test/test_auth.py`: `/api/display`→patient, `/api/patients`·`/api/ocr`→staff, `/api/console류`→admin 단위검증 갱신.
- 수동: 비로그인 `/`→환자패널(로그인 안 뜸) / staff `/`→회진 노출 / staff `/console`→`/` 리다이렉트 / patient `/patients`→`/` 리다이렉트.
- `tsc --noEmit` 통과.
