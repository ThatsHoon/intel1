# 대시보드 카메라 GUI (탐지 RGB + depth) — 설계

**Goal:** nurse_tracking이 OAK-D RGB-D로 무엇을 어떻게 탐지하는지 대시보드(콘솔)에서 시각 확인.
탐지 오버레이 RGB + depth 컬러맵을 base64 JPEG로 RTDB에 저fps 송출해 무-ROS 웹이 렌더.

**Architecture:** 로봇측 `camera_bridge`(db_bridge) 노드가 프레임을 다운스케일 JPEG→base64로
`{ns}/camera`에 ~3fps 적재. 웹 패널이 열려 요청(`{ns}/camera/request {on,ts}` 하트비트)일 때만
인코딩(RTDB 부하 최소). 백엔드 SSE로 프레임 push, 콘솔 패널이 `<img data:>`로 표시.

---

## 회진모드 체인 감사 결론(별건)
웹 `saveMode(start,round)`→`cmd`→`db_node` 중계→`arbiter`→`mode/round/set`→`tracker`→YOLO(`nurse`
라벨 일치)→`cmd_vel`→safety_gate. **코드 결함 없음.** RGB compressed+depth compressedDepth+
ApproximateTimeSynchronizer(slop 50ms)+BEST_EFFORT QoS 확인. 10fps는 OAK-D 튜닝값(robot-side).
동작 전제는 런타임(OAK-D 스트리밍·create3·cmd-bridge 반영·순차기동).

## 컴포넌트

### 1. `camera_bridge` 노드 (db_bridge 신규)
- **구독(요청 on일 때만 동적 생성)**: `/nurse_tracker/annotated_image`(raw Image bgr8, 탐지 오버레이),
  `/{ns}/oakd/stereo/image_raw/compressedDepth`(depth), `/{ns}/oakd/rgb/image_raw/compressed`(폴백 RGB).
- **게이트**: `{ns}/camera/request {on,ts}` listen → on이고 ts 신선(<`request_ttl`=6s)일 때만 활성.
- **활성 시 `camera_fps`(3Hz)**: rgb_src(annotated 우선, 없으면 raw)→width 320 리사이즈→JPEG(q60)→base64;
  depth→decode(12B+PNG, 16UC1 mm)→clip[300,4000]→정규화→`applyColorMap(JET)`→리사이즈→JPEG→base64.
  RTDB `{ns}/camera` update `{rgb, depth, ts, w, h, src}`.
- **비활성**: 구독 해제(→ tracker annotated lazy off) + 인코딩/쓰기 중단.
- params: `namespace, fb_cred, fb_db_url, camera_fps=3.0, width=320, jpeg_quality=60, request_ttl=6.0`.

### 2. 백엔드 (`web/backend`)
- `POST /api/camera/<ns>/request {on}` → `fb_read.camera_request(ns,on)` → `{ns}/camera/request` set(ts 주입).
- `GET /api/camera/<ns>/stream` (SSE) → `{ns}/camera` 변경을 프레임으로 push.
- RBAC: `/api/camera`는 `/api/` 기본 admin(콘솔 admin과 일치 — 변경 불요).

### 3. 프론트 (콘솔 admin)
- `CameraPanel` 컴포넌트: 마운트 시 request on 하트비트(3s) + SSE 구독; 언마운트 시 request off + 정리.
- 렌더: `<img src="data:image/jpeg;base64,{rgb}">`(탐지 RGB) | depth 컬러맵, 갱신 fps·src 표시.
- 콘솔 레이아웃 하단에 배치.

## 부하/검증
- 320px@~3fps 2장 ≈ 240KB/s, 패널 열렸을 때만.
- 검증: camera_bridge 인코딩/게이트 순수로직(가능한 범위) + py_compile·colcon build, 백엔드 py_compile, 프론트 tsc.
