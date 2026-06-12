# HERABot 시스템 아키텍처 다이어그램 — 계층형 Graphviz DOT 프롬프트 세트

- **작성일**: 2026-06-09
- **목표**: 원본 PDF(`별첨.SystemArchitectureDiagram_HERABot`) 수준의 고밀도 복합 다이어그램을, LLM에 단계별 프롬프트를 주어 **Graphviz DOT** 코드로 안정적으로 재현
- **산출 도구**: Graphviz DOT (`digraph`)
- **접근**: 단일 통합 프롬프트가 아닌 **계층형 5단계 프롬프트 세트** (누적 생성)

---

## 1. 원본 분석 요약

**HERABot** = TurtleBot4 기반 AMR 2대로 구성된 **병원 낙상 감지·구조 시스템**. 단순 박스 다이어그램이 아니라 **배포(deployment) + 상태머신(state machine) + 데이터플로우(topic flow)** 가 한 장에 중첩된 고밀도 복합 다이어그램.

| 영역 | 내용 |
|------|------|
| **PC3 (System Monitor)** | 카메라 스트리밍, 'Fall down' 알림, DB 업데이트(robot_id·event_time·x/y/z·snapshot), 버튼 기반 "상황 종료"(end_time) 처리 |
| **PC1 / PC2 (Operator PC)** | 로봇별 상태머신: Patrol(Mode1)→Alert(Mode2)→Rescue(Mode3)+Charging. localization/view_robot/nav2/RViz2, FastDDS·Ubuntu 22.04·ROS 2 Humble |
| **Robot5(AMR1)/Robot6(AMR2)** | Create3 + RPi4B + RPLIDAR A1M8 + OAK-D-Pro + 26Wh 배터리 + Status LED. turtlebot4_bringup/navigation/viz/description, depthai_ros_driver/rplidar_ros |
| **감지 로직** | yolo11n-pose → 낙상 기준(짧은 수직 길이·큰 몸통 각도·어깨/엉덩이 유사 높이·넓은 수평 bbox) → rgb/depth/camera_info로 target point 계산 → map 좌표 변환 |
| **협조 동작** | 한쪽 로봇 감지 시 다른 로봇이 Station→Target 이동, Beep, Aid Kit 전달 |
| **네트워크** | WiFi 6 AP + Gigabit Ethernet Switch, FastDDS topic 전파 |

**핵심 좌표**
- Robot5 Station 5: `x=-2.3076, y=0.1667, qx=0, qy=0, qz=-0.9062, qw=0.4228`
- Robot6 Station 6: `x=1.2671, y=5.4468, qx=0, qy=0, qz=0.4346, qw=0.906`

**주요 토픽**
- `/robotX/navigate_to_pose <PoseStamped>` (frame_id='map')
- `/target_point_X <PointStamped>`, `/tf_target_point_X <PointStamped>`
- `/arrival_target_X <Bool>`, `/arrival_station_X <Bool>`, `/beep_finished_X <Bool>`, `/return_to_patrol <Bool>`
- `/robotX/cmd_audio <AudioNoteVector>` — Alert: `880Hz0.3s/440Hz0.3s ×4`, Beep: `550Hz0.3s·0Hz0.1s·550Hz0.3s·0Hz1s ×2`
- `/robotX/oakd/rgb/camera_info <CameraInfo>`, `/robotX/oakd/rgb/image_raw/compressed <CompressedImage>`, `/robotX/oakd/stereo/image_raw <Image>`
- `/robotX/dock <DockControl>`, `/robotX/undock <DockControl>`

---

## 2. 설계: 5단계 누적 프롬프트

```
[P0 마스터]  전역 규칙·스타일·레이아웃 골격 → 빈 클러스터 5개 생성
   ├─ [P1] PC3 System Monitor (낙상 알림·DB·상황종료)
   ├─ [P2] PC1/PC2 Operator (Patrol→Alert→Rescue→Charging 상태머신)
   ├─ [P3] Robot5/Robot6 HW·ROS2 노드 스택 + 감지 파이프라인
   └─ [P4] 토픽 배선(레인 간 교차 엣지) + 네트워크 + 범례
[P5 검증]   품질 체크리스트로 자가 점검·수정
```

각 단계는 **이전 단계의 DOT 출력을 입력으로 받아 누적**한다. 고밀도 그래프를 한 번에 생성하면 레인 간 교차 엣지에서 레이아웃이 깨지기 쉬우므로, 단계 분할로 검증·국소 수정을 가능하게 한다.

---

### P0 — 마스터 프롬프트 (골격·전역 규칙)

> 너는 Graphviz DOT 전문가다. 병원 낙상감지 로봇 시스템 "HERABot"의 시스템 아키텍처 다이어그램을 `digraph`로 그린다. 이번 단계에서는 **전역 골격만** 만든다.
>
> **전역 설정**
> - `rankdir=TB`, `compound=true`, `newrank=true`, `splines=ortho`, `nodesep=0.4`, `ranksep=0.6`, `fontname="Helvetica"`, 용지 세로 A1 비율
> - 노드 기본: `shape=box, style=filled, fillcolor=white, color=black`
> - 의미별 노드 스타일 정의: **process**=`box`, **decision**=`diamond`, **topic/IO**=`shape=parallelogram, fontsize=9`(ROS 토픽용), **terminator**=`shape=box, style="rounded,filled"`
>
> **레인(클러스터) 골격** — 다음 5개 `subgraph cluster_*`만 생성하고 내부는 라벨 placeholder 1개씩만 둔다:
> 1. `cluster_pc3` — label "PC3 — System Monitor"
> 2. `cluster_pc1` — label "PC1 — Operator (Robot5/AMR1)"
> 3. `cluster_pc2` — label "PC2 — Operator (Robot6/AMR2)"
> 4. `cluster_robot5` — label "Robot5 (AMR1) — TurtleBot4"
> 5. `cluster_robot6` — label "Robot6 (AMR2) — TurtleBot4"
>
> **배치 의도**: 상단 PC3 → 중단 좌 PC1 / 우 PC2 → 하단 좌 Robot5 / 우 Robot6. 좌우 대칭(Robot5계열=좌, Robot6계열=우).
>
> 클러스터마다 `style=rounded, color=gray40, penwidth=1.5`. 출력은 **컴파일 가능한 완전한 DOT 한 덩어리**. 다음 단계에서 내부를 채울 것이므로 placeholder 노드는 명확히 주석 표시할 것.

---

### P1 — PC3 System Monitor

> 이전 DOT의 `cluster_pc3` 내부를 채운다. 다음 흐름을 decision/process 노드로 구성:
> - `Robot5/Robot6 Camera Streaming` (process) → `'Fall down' incident occurred` (process)
> - decision: `Fall down detected?` → Yes면 `DB Update (robot_id, event_time, x, y, z, snapshot)` → `Snapshot Capture`
> - `Waiting` → decision `Situation Over (Rescued)?` → Yes `Press the Button "상황 종료"` → `DB Update (end_time)`
> - No 경로는 `Waiting`으로 되돌아가는 루프 엣지
>
> 같은 의미 노드는 P0에서 정의한 스타일 재사용. **다른 클러스터는 절대 수정하지 말 것.** 출력은 전체 누적 DOT.

---

### P2 — PC1/PC2 Operator 상태머신

> `cluster_pc1`(Robot5)과 `cluster_pc2`(Robot6) 내부를 **좌우 대칭**으로 채운다. 각 PC는 4개 모드 상태머신:
>
> - **Patrol Mode (Mode 1)**: `Patrol (Camera On)` → decision `'Fall down' Detected (over 0.5s)?`
> - decision `Low Battery (20%)?` → Yes → **Charging Mode**: `dock` → decision `Charging Complete (95%)?` → Yes → `undock` → Patrol 복귀
> - 'Fall down' Yes → **Alert Mode (Mode 2)**: `Convert to map coordinates` → **Rescue Mode (Mode 3)**
> - Rescue Mode 세부(자기 로봇 감지 vs 상대 로봇 감지로 분기):
>   - 자기 감지: `Navigate to Target` → `Arrival to Target` → `Beep at Target`
>   - 상대 감지: `Navigate to Station` → `Beep at Station (4s one-shot timer)` → `Save Target Point` → `Navigate to Target from Station` (Aid Kit 전달)
> - `Button Pressed "상황 종료"` → `Waiting` → Patrol 복귀
>
> 각 클러스터 하단에 **환경 박스**(process, 좌측정렬 멀티라인 라벨): `FastDDS / Ubuntu 22.04 LTS / ROS 2 Humble / RViz2: /scan·/map·/tf·/odom·/image_raw 시각화, Set Goal Pose→Nav2, Set Initial Pose→AMCL / localization·view_robot·nav2`.
>
> Robot5 station 좌표 `x=-2.3076, y=0.1667, qz=-0.9062, qw=0.4228`, Robot6 station 좌표 `x=1.2671, y=5.4468, qz=0.4346, qw=0.906`를 해당 Navigate to Station 노드에 명시. 다른 클러스터는 수정 금지. 전체 누적 DOT 출력.

---

### P3 — Robot HW·ROS2 노드 스택 + 감지 파이프라인

> `cluster_robot5`/`cluster_robot6` 내부를 좌우 대칭으로 채운다. 각 로봇은 세 부분:
>
> **(A) ROS2 패키지 스택** (process, 좌측정렬 멀티라인 라벨 노드들):
> - `turtlebot4_bringup`: robot_state_publisher(URDF→/robot_description,/tf,/tf_static), rplidar_ros(/scan), depthai_ros_driver(/oakd/rgb,/oakd/stereo,/camera_info), diagnostics(/battery_state), HMI(buttons,LED,audio)
> - `turtlebot4_navigation`: AMCL(localization), controller_server(→/cmd_vel), map_server
> - `turtlebot4_viz`, `turtlebot4_description`, `depthai_ros_driver`, `rplidar_ros`
> - `Communication`: FastDDS가 sensor·TF 토픽을 Operator PC로 publish, /cmd_vel을 Create3로 전송
>
> **(B) 하드웨어 목록** (별도 process 노드): iRobot Create 3, Raspberry Pi 4B, RPLIDAR A1M8, OAK-D-Pro, 26Wh 리튬이온 배터리, Status LED(MTR/COMM/Wi-fi/Battery/Power)
>
> **(C) 감지 파이프라인** (decision 포함): `rgb,depth camera data receive` → `'Person' Detection (yolo11n-pose)` → decision `'Fall down' criteria?` (짧은 수직 길이·큰 몸통 각도·어깨/엉덩이 유사 높이·넓은 수평 bbox) → Yes → `Calculate target point (rgb+depth+camera_info)`.
>
> 전체 누적 DOT 출력, 타 클러스터 수정 금지.

---

### P4 — 토픽 배선 + 네트워크 + 범례

> 이제 **클러스터 간 ROS2 토픽 엣지**를 추가한다. 토픽은 `parallelogram` 노드(fontsize=9)로 표현하고 publisher→topic→subscriber 방향 엣지로 연결. `ltail`/`lhead`로 클러스터 경계에 부착.
>
> 주요 토픽(타입 포함 라벨):
> - `/robot5/navigate_to_pose <PoseStamped> frame_id='map'`, `/robot6/navigate_to_pose <PoseStamped>`
> - `/arrival_target_5 <Bool>`, `/arrival_target_6 <Bool>`, `/arrival_station_5 <Bool>`, `/arrival_station_6 <Bool>`
> - `/beep_finished_5 <Bool>`, `/beep_finished_6 <Bool>`, `/return_to_patrol <Bool>`
> - `/robot5/cmd_audio <AudioNoteVector>` (Alert 880Hz0.3s/440Hz0.3s ×4; Beep 550Hz0.3s·0Hz0.1s·550Hz0.3s·0Hz1s ×2), `/robot6/cmd_audio` 동일
> - `/target_point_5 <PointStamped>`, `/tf_target_point_5 <PointStamped>` (Robot6도 동일)
> - 카메라: `/robotX/oakd/rgb/camera_info <CameraInfo>`, `/robotX/oakd/rgb/image_raw/compressed <CompressedImage>`, `/robotX/oakd/stereo/image_raw <Image>`
> - `/robotX/dock <DockControl>`, `/robotX/undock <DockControl>`
>
> 배선 규칙: 카메라/감지 토픽은 Robot→PC3, navigate/audio/dock 명령은 PC→Robot, arrival/beep/target 상태 토픽은 PC↔PC3. 협조 동작(Robot5 감지→Robot6 station 이동)을 위한 교차 엣지 포함.
>
> 마지막에 `cluster_network` 추가: "ROS2 Humble WiFi — WiFi 6 AP, Gigabit Ethernet Switch, FastDDS". 그리고 **범례**(cluster_legend): process/decision/topic/terminator 모양 의미 표기. 전체 완성 DOT 출력.

---

### P5 — 품질 검증 체크리스트

> 생성된 DOT을 다음 기준으로 자가 점검하고 위반 시 수정한 최종 DOT을 출력:
> 1. `dot -Tpng`로 **컴파일 에러 없이** 렌더되는가 (구문·중괄호·중복 노드 ID)
> 2. 5개 PC/로봇 클러스터 + network + legend가 모두 존재하는가
> 3. 좌우 대칭(Robot5=좌 / Robot6=우)이 유지되는가
> 4. 4개 모드(Patrol/Alert/Rescue/Charging) 상태 전이가 끊김 없이 연결되는가
> 5. 원본의 핵심 토픽(navigate_to_pose, cmd_audio, target_point, arrival/beep/dock, camera 3종)이 모두 엣지로 존재하는가
> 6. 좌표값·주파수·낙상 기준 등 **수치 라벨이 누락/오타 없이** 정확한가
> 7. 교차 엣지가 노드를 관통해 가독성을 해치지 않는가 (`splines=ortho` 유지, 필요 시 `constraint=false`)

---

## 3. 비고 — draw.io MCP 경로

이 스펙은 도구 독립적인 Graphviz DOT 프롬프트 세트다. 별도로 로컬 설치한 `drawio-mcp-server`(MCP, 에디터 포트 3030, WS 3333)로도 동일 구조를 작도 가능하다. DOT으로 먼저 구조를 확정한 뒤, 필요 시 draw.io MCP로 시각 편집/내보내기(XML·SVG·PNG)하는 워크플로우를 권장한다.
