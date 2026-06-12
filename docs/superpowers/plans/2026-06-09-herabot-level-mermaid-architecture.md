# HERA급 Mermaid 아키텍처 문서 개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docs/architecture/05_mermaid_architecture.md` 를 HERA(HERABot) 도면 수준(타입 명시 엣지 + SW/HW 스택 + 상태머신 + 네트워크 + 결정기준)으로 전면 재작성하고, 오늘 변경된 미션 동작(mission_cancel·우선순위 선점·15s 시작워치독/무제한 완료)을 반영한다.

**Architecture:** 단일 파일을 섹션(다이어그램)별로 누적 작성한다. §1 마스터 오버뷰 + §2~§6 디테일(컴퓨트/네트워크, ROS 노드 그래프, 상태머신, 시나리오 플로우, 인터페이스 표). 각 섹션 작성 후 무의존 구조 검증 스크립트로 mermaid 구문을 검사한다.

**Tech Stack:** Markdown + Mermaid v10 (graph/flowchart/stateDiagram-v2), 검증은 `docs/architecture/check_mermaid.py`(Python 표준 라이브러리만).

**참조 진실값(스펙 §권위 사실):** dock/undock=`irobot_create_msgs/action/Dock·Undock`; `START_TIMEOUT=15.0s`·완료 무제한; 우선순위 shutdown/reboot/ros_restart 9·goto 7·dock/undock 6·intake 5·round 4·errand 3·guide 2·patrol/patrol_mission 1·default 5; `NON_PREEMPTIBLE=dock,undock,ros_restart,reboot,shutdown,patrol_mission`; 피드백 `accepted→running→done|failed`(+db측 `preempted`/`timeout`); 홈 dock `x=-0.354229,y=-0.118972,yaw=-0.0042011`.

---

## File Structure

- **Create:** `docs/architecture/check_mermaid.py` — 무의존 mermaid 블록 구조 검증기(펜스·타입선언·subgraph/end·괄호/따옴표 균형).
- **Overwrite:** `docs/architecture/05_mermaid_architecture.md` — Task 1에서 헤더+§구조로 새로 시작, Task 2~7에서 섹션 누적.

검증 명령(모든 섹션 공통):
```bash
cd /home/rokey/MediCart && python3 docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md
```

---

## Task 1: 검증 스크립트 + 새 파일 헤더

**Files:**
- Create: `docs/architecture/check_mermaid.py`
- Overwrite: `docs/architecture/05_mermaid_architecture.md`

- [ ] **Step 1: 검증 스크립트 작성**

`docs/architecture/check_mermaid.py`:
```python
#!/usr/bin/env python3
"""check_mermaid.py — md 내 ```mermaid 블록 구조 검증(오프라인·표준 라이브러리만).

완전 파서가 아니라 자주 깨지는 항목 검사:
  · 다이어그램 타입 선언(graph/flowchart/sequenceDiagram/stateDiagram...)
  · 블록 내부 펜스(```) 잔존 금지
  · subgraph/end 균형, []·{}·() 균형, 따옴표(") 짝수
"""
import re
import sys

VALID = ("graph ", "flowchart ", "sequenceDiagram", "stateDiagram",
         "erDiagram", "classDiagram", "graph\n", "flowchart\n")


def check(path):
    text = open(path, encoding="utf-8").read()
    blocks = re.findall(r"```mermaid\n(.*?)```", text, re.S)
    if not blocks:
        print(f"FAIL {path}: mermaid 블록 없음")
        return 1
    errs = []
    for i, b in enumerate(blocks, 1):
        first = next((ln.strip() for ln in b.splitlines() if ln.strip()), "")
        if not first.startswith(VALID):
            errs.append(f"#{i}: 다이어그램 타입 선언 누락(첫 줄='{first[:40]}')")
        if "```" in b:
            errs.append(f"#{i}: 블록 내부에 펜스(```) 잔존")
        sg = len(re.findall(r"\bsubgraph\b", b))
        en = len(re.findall(r"^\s*end\s*$", b, re.M))
        if sg != en:
            errs.append(f"#{i}: subgraph({sg}) != end({en})")
        for op, cl in (("[", "]"), ("{", "}"), ("(", ")")):
            if b.count(op) != b.count(cl):
                errs.append(f"#{i}: '{op}{cl}' 불균형 {b.count(op)}/{b.count(cl)}")
        if b.count('"') % 2:
            errs.append(f'#{i}: 따옴표(") 홀수')
    if errs:
        print(f"FAIL {path} ({len(blocks)} blocks):")
        for e in errs:
            print("  -", e)
        return 1
    print(f"OK {path}: {len(blocks)} mermaid blocks 통과")
    return 0


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "docs/architecture/05_mermaid_architecture.md"
    sys.exit(check(p))
```

- [ ] **Step 2: 새 파일 헤더 작성(기존 264줄 덮어쓰기)**

`docs/architecture/05_mermaid_architecture.md` 를 다음으로 **새로 생성(덮어쓰기)**:
```markdown
# MediCart Architecture (Mermaid · HERA급)

> 통합 브랜치(`integration` = main ↔ jaehoon) 기준. 참조 수준: HERABot System Architecture Diagram.
> namespace 기본 `robot6` — **robot3(AMR1)도 PC1에서 동일 구조로 동작**(노드·토픽 네임스페이스만 `robot3`).
> 구성: §1 마스터 오버뷰 → §2 컴퓨트·네트워크 → §3 ROS 노드 그래프 → §4 상태머신 → §5 시나리오 플로우 → §6 인터페이스 표.
> 텍스트 상세는 `01_system_architecture.md`~`04_db_schema.md`, 시각본은 `diagrams/` 참고.

---
```

- [ ] **Step 3: 검증기 동작 확인(아직 mermaid 없음 → FAIL 기대)**

Run: `cd /home/rokey/MediCart && python3 docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md`
Expected: `FAIL ...: mermaid 블록 없음` (정상 — 아직 다이어그램 미작성)

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md
git commit -m "docs(arch): mermaid 검증기 + HERA급 문서 헤더"
```

---

## Task 2: §1 마스터 오버뷰

**Files:**
- Modify: `docs/architecture/05_mermaid_architecture.md` (append)

- [ ] **Step 1: §1 섹션 추가**

파일 끝에 추가:
````markdown
## 1. 마스터 오버뷰 (전체 배치)

```mermaid
graph TD
  USER["운영자·간호사·환자<br/>브라우저"] -->|"HTTPS / cloudflared"| FE

  subgraph PC3["PC3 — 웹 (ROS 노드 없음)"]
    FE["Next.js :3000<br/>/console /map /patients /intake /ocr /display /qr"]
    BE["Flask :5000<br/>REST + SSE · RBAC(admin/staff/patient)"]
    FE -->|"/api/* · /api/stream(SSE)"| BE
  end

  subgraph FB["Firebase RTDB — 크로스-PC 버스"]
    POOL["robot6/mission_pool<br/>+ mission_status / mission_log"]
    DATA["patients · rooms · targets<br/>intake_pending · display · ocr · telemetry · alerts"]
  end

  subgraph PC1["PC1 — robot3 전담"]
    R3["loc3 · nav3 · db_bridge · mission_manager<br/>nurse_tracker · obstacle_detector"]
  end

  subgraph PC2["PC2 — robot6 전담 (FastDDS Discovery :11811 · DOMAIN 6)"]
    DB["db_node<br/>(db_bridge)"]
    MM["mission_manager_node<br/>(중재 허브 · cmd_vel 단독소유)"]
    SRV["prescription_server · rooms_server · display_bridge"]
    PERC["인지: identifier_node(A) · tracker_node(B) · obstacle_node"]
    NAV["Nav2 + AMCL + map_server"]
  end

  subgraph AMR["robot6 (turtlebot4 · RPi4B)"]
    HW["Create3 · OAK-D-Pro · RPLIDAR A1M8"]
  end

  BE <-->|"firebase-admin"| POOL
  BE <-->|"firebase-admin"| DATA
  DB <-->|"listen / write"| POOL
  DB -->|"/robot6/mission_request · mission_cancel"| MM
  MM -->|"/robot6/mission_feedback"| DB
  SRV <-->|"RTDB"| DATA
  MM --> PERC
  MM -->|"navigate_to_pose · dock/undock"| NAV
  MM -->|"/robot6/cmd_vel"| HW
  NAV --> HW
  HW -->|"/scan /oakd/* /odom /battery_state /dock_status"| PERC
  HW -. "telemetry" .-> DB
  PC1 <-->|"firebase-admin"| FB
```

> robot3(AMR1)은 PC1에서 위 robot6 스택과 동일하게 동작하며 네임스페이스만 `robot3`.
````

- [ ] **Step 2: 검증**

Run: `cd /home/rokey/MediCart && python3 docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md`
Expected: `OK ...: 1 mermaid blocks 통과`

- [ ] **Step 3: 커밋**

```bash
cd /home/rokey/MediCart
git add docs/architecture/05_mermaid_architecture.md
git commit -m "docs(arch): §1 마스터 오버뷰"
```

---

## Task 3: §2 컴퓨트 & 네트워크 레이아웃

**Files:**
- Modify: `docs/architecture/05_mermaid_architecture.md` (append)

- [ ] **Step 1: §2 섹션 추가**

파일 끝에 추가:
````markdown
## 2. 컴퓨트 & 네트워크 레이아웃

```mermaid
graph TB
  subgraph NET["네트워크 — ROS2 Humble · WiFi6 AP · Gigabit Ethernet Switch · cloudflared(외부)"]
    direction TB

    subgraph OPC["운영 PC (PC1=robot3 / PC2=robot6 동일 구성)"]
      OS["Ubuntu 22.04 LTS · ROS2 Humble · FastDDS Discovery Server :11811 (DOMAIN 6)"]
      VIZ["RViz2 — 시각화 /scan /map /tf /odom /image_raw · Set Goal Pose→Nav2 · Set Initial Pose→AMCL"]
      LOC["loc6 — AMCL (bond_timeout 10s 패치)"]
      NV["nav6 — Nav2 bt_navigator · controller_server · planner_server · map_server (bond 패치)"]
      APP["앱 패키지 — db_bridge · mission_manager · nurse_tracker · obstacle_detector · medi_interfaces"]
    end

    subgraph TB4["robot6 — turtlebot4 (RPi 4B)"]
      BR["turtlebot4_bringup — robot_state_publisher(/robot_description /tf /tf_static) · rplidar_ros(/scan) · depthai_ros_driver(/oakd/rgb /oakd/stereo /camera_info) · diagnostics(/battery_state) · HMI(버튼/LED/오디오)"]
      TNAV["turtlebot4_navigation — AMCL · controller_server · planner_server · bt_navigator · map_server"]
      HWB["HW — iRobot Create3 · RPLIDAR A1M8 · OAK-D-Pro · 배터리 · Status LED(MTR/COMM/WiFi/Battery/Power)"]
    end

    subgraph WPC["PC3 — 웹"]
      WEB["Next.js :3000 · Flask :5000 · cloudflared 터널 (ROS 노드 없음, RTDB 읽기/쓰기만)"]
    end
  end

  OPC <-->|"FastDDS (sensor·TF·cmd_vel)"| TB4
  WPC <-->|"Firebase RTDB"| OPC
```
````

- [ ] **Step 2: 검증**

Run: `cd /home/rokey/MediCart && python3 docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md`
Expected: `OK ...: 2 mermaid blocks 통과`

- [ ] **Step 3: 커밋**

```bash
cd /home/rokey/MediCart
git add docs/architecture/05_mermaid_architecture.md
git commit -m "docs(arch): §2 컴퓨트·네트워크 레이아웃"
```

---

## Task 4: §3 ROS 노드 그래프 (타입 명시)

**Files:**
- Modify: `docs/architecture/05_mermaid_architecture.md` (append)

- [ ] **Step 1: §3 섹션 추가 (통합 그래프 + 기능별 분해)**

파일 끝에 추가:
````markdown
## 3. ROS 노드 그래프 (토픽/서비스/액션 — name + type + 값)

### 3.1 미션 오케스트레이션 — db_node ↔ mission_manager

```mermaid
graph LR
  POOL[("RTDB robot6/mission_pool")] -->|"listen"| DB["db_node"]
  DB -->|"status/progress write"| POOL
  DB -->|"/robot6/mission_request<br/>std_msgs/String {id,action,params,mode}"| MM["mission_manager_node"]
  DB -->|"/robot6/mission_cancel<br/>std_msgs/String {id,reason} (선점)"| MM
  MM -->|"/robot6/mission_feedback<br/>std_msgs/String {id,status,detail,ts}"| DB
  MM -->|"/robot6/robot_mode<br/>std_msgs/String"| MON["모니터/웹"]
  MM -->|"/robot6/cmd_vel<br/>geometry_msgs/Twist (단독소유)"| C3["Create3 base"]
  SCAN["RPLIDAR"] -->|"/robot6/scan<br/>sensor_msgs/LaserScan"| MM
  DS["Create3"] -->|"/robot6/dock_status<br/>irobot_create_msgs/DockStatus"| MM
  MM -. "내부" .-> ARB["mode_arbiter"]
  MM -. "내부" .-> NEX["nav_executor"]
  MM -. "내부" .-> MEX["mission_executor"]
  MM -. "내부" .-> SEQ["MissionSequencer (patrol_mission)"]
  NEX -->|"/robot6/navigate_to_pose<br/>nav2_msgs/NavigateToPose · frame_id='map'"| NAV2["Nav2 bt_navigator"]
  NEX -->|"/robot6/dock · /robot6/undock<br/>irobot_create_msgs/action/Dock·Undock"| C3
  MEX -->|"subprocess: ros2 action send_goal / ssh"| C3
```

### 3.2 모드 중재 — mode_arbiter (REACTIVE 계약)

```mermaid
graph LR
  ARB["mode_arbiter<br/>(mission_manager 내부)"] -->|"/robot6/mode/{mode}/set<br/>std_msgs/String (latched) {active,params}"| M["mode node (예: round)"]
  M -->|"/robot6/mode/{mode}/cmd_vel<br/>geometry_msgs/Twist"| ARB
  M -->|"/robot6/mode/{mode}/status<br/>std_msgs/String {state}"| ARB
  OB["obstacle_node"] -->|"/obstacle_detector/ground_status<br/>std_msgs/String"| ARB
  ARB -->|"우선순위 선택 + safety_gate (lidar 0.30m / depth 0.20m)"| OUT["/robot6/cmd_vel<br/>geometry_msgs/Twist"]
```

### 3.3 시나리오 A 인지 — identifier_node + db_bridge

```mermaid
graph LR
  OAK["OAK-D"] -->|"/robot6/oakd/rgb/image_raw<br/>sensor_msgs/Image"| ID["identifier_node<br/>(YOLO + QR + 병실검증)"]
  PAT["patrol_mode_node"] -->|"/robot6/identify/start<br/>std_msgs/String"| ID
  ID -->|"/robot6/patient_identified<br/>medi_interfaces/PatientIdentified"| PAT
  ID -->|"/robot6/patient_identified"| DBR["display_bridge → RTDB display/current_patient"]
  ID -->|"/robot6/db/get_prescription<br/>medi_interfaces/GetPrescription"| PS["prescription_server"]
  PS -->|"PatientInfo + MedicineInfo[]"| ID
  PS <-->|"RTDB patients/rooms"| RTDB[("Firebase RTDB")]
  PAT -->|"/robot6/db/list_rooms<br/>medi_interfaces/ListRooms"| RS["rooms_server"]
  RS -->|"room_ids/xs/ys/yaws"| PAT
  PAT -->|"/robot6/navigate_to_pose<br/>nav2_msgs/NavigateToPose"| NAV2["Nav2"]
```

### 3.4 시나리오 B 추종 — nurse_tracker (round)

```mermaid
graph LR
  OAK["OAK-D"] -->|"/robot6/oakd/rgb/image_raw/compressed<br/>sensor_msgs/CompressedImage"| TR["tracker_node<br/>(YOLO11s best.pt + ByteTrack)"]
  OAK -->|"/robot6/oakd/stereo/image_raw/compressedDepth<br/>sensor_msgs/CompressedImage"| TR
  CALL["mission_manager / 웹"] -->|"/robot6/start_tracking<br/>std_srvs/Trigger"| TR
  TR -->|"/robot6/mode/round/cmd_vel<br/>geometry_msgs/Twist"| ARB["mode_arbiter"]
  TR -->|"/robot6/mode/round/status<br/>std_msgs/String"| ARB
  TR -->|"/nurse_tracker/target<br/>std_msgs/String · /nurse_tracker/annotated_image<br/>sensor_msgs/Image"| VIS["시각화/디버그"]
  ARB -. "/robot6/mode/round/set" .-> TR
```

### 3.5 장애물 안전 — obstacle_detector

```mermaid
graph LR
  OAK["OAK-D stereo"] -->|"/robot6/oakd/stereo/image_raw/compressedDepth<br/>sensor_msgs/CompressedImage"| OB["obstacle_node<br/>(depth→지면 평면 SVD)"]
  OAK -->|"/robot6/oakd/stereo/camera_info<br/>sensor_msgs/CameraInfo"| OB
  OB -->|"/obstacle_detector/ground_cloud<br/>sensor_msgs/PointCloud2"| RV["RViz/디버그"]
  OB -->|"/obstacle_detector/ground_status<br/>std_msgs/String"| MM["mission_manager safety_gate"]
```

### 3.6 자율주행 · 하드웨어

```mermaid
graph LR
  RP["RPLIDAR"] -->|"/robot6/scan<br/>sensor_msgs/LaserScan"| AMCL["AMCL (loc)"]
  RP --> NAV2["Nav2"]
  MAP["map_server"] -->|"/robot6/map<br/>nav_msgs/OccupancyGrid"| NAV2
  AMCL -->|"map→odom TF · /robot6/amcl_pose<br/>geometry_msgs/PoseWithCovarianceStamped"| NAV2
  C3["Create3"] -->|"/robot6/odom · /robot6/battery_state · /robot6/dock_status<br/>nav_msgs/Odometry · sensor_msgs/BatteryState · irobot_create_msgs/DockStatus"| SUB["telemetry→RTDB→웹"]
  OAK["OAK-D"] -->|"/robot6/oakd/rgb/* · /robot6/oakd/stereo/*"| PERC["인지 노드들"]
```
````

- [ ] **Step 2: 검증**

Run: `cd /home/rokey/MediCart && python3 docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md`
Expected: `OK ...: 8 mermaid blocks 통과`

- [ ] **Step 3: 커밋**

```bash
cd /home/rokey/MediCart
git add docs/architecture/05_mermaid_architecture.md
git commit -m "docs(arch): §3 ROS 노드 그래프(타입 명시) + mission_cancel"
```

---

## Task 5: §4 상태머신 (미션 라이프사이클 + 모드 중재)

**Files:**
- Modify: `docs/architecture/05_mermaid_architecture.md` (append)

- [ ] **Step 1: §4 섹션 추가**

파일 끝에 추가:
````markdown
## 4. 상태머신

### 4.1 미션 라이프사이클 (db_node 오케스트레이션 — 신규 동작)

```mermaid
stateDiagram-v2
  [*] --> pending : web push (mission_pool)
  pending --> sent : 우선순위→ts 선택 후 mission_request 발행
  sent --> running : accepted/running 수신
  sent --> failed : 15s 내 accepted 미수신 (START_TIMEOUT)
  running --> done : mission_feedback done
  running --> failed : mission_feedback failed
  running --> preempted : 더 높은 우선순위 도착 (현재 폐기·드롭)
  done --> [*]
  failed --> [*]
  preempted --> [*]
  note right of running
    완료 타임아웃 없음 (무제한 대기)
    NON_PREEMPTIBLE(dock/undock/시스템/patrol_mission)은 선점 안 함
    nav_executor는 create3 진행 중 cancel을 goal 취소 없이 안전 처리
  end note
```

### 4.2 모드 중재 — 우선순위 선점/복귀 + safety_gate

```mermaid
stateDiagram-v2
  [*] --> idle
  idle --> active : start mode (active set 추가)
  active --> preempted_mode : 더 높은 우선순위 모드 활성
  preempted_mode --> active : 상위 모드 종료 → 복귀
  active --> idle : stop/clear 또는 status done/failed
  active --> lost : status 무응답 3s (lost abort)
  lost --> idle
  note right of active
    우선순위: goto 7 (운영자) > intake 5 > round 4 > errand 3 > guide 2 > patrol 1
    REACTIVE 모드: cmd_vel은 safety_gate 통과 (전방 lidar 0.30m / depth 0.20m, 전진만 차단)
  end note
```
````

- [ ] **Step 2: 검증**

Run: `cd /home/rokey/MediCart && python3 docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md`
Expected: `OK ...: 10 mermaid blocks 통과`

- [ ] **Step 3: 커밋**

```bash
cd /home/rokey/MediCart
git add docs/architecture/05_mermaid_architecture.md
git commit -m "docs(arch): §4 상태머신(미션 라이프사이클·모드 중재)"
```

---

## Task 6: §5 시나리오 플로우

**Files:**
- Modify: `docs/architecture/05_mermaid_architecture.md` (append)

- [ ] **Step 1: §5 섹션 추가**

파일 끝에 추가:
````markdown
## 5. 시나리오 / 기능 플로우

### 5.1 시나리오 A — 자율순찰 + QR신원 + 문진

```mermaid
flowchart TD
  S0([Station 도킹]) --> U0["Undock<br/>/robot6/undock (irobot_create_msgs/Undock)"]
  U0 --> L0["병상 waypoint 획득<br/>ListRooms /robot6/db/list_rooms"]
  L0 --> P0["다음 병실 이동<br/>NavigateToPose /robot6/navigate_to_pose"]
  P0 --> ID["재실+신원 확인<br/>identifier_node → /robot6/patient_identified"]
  ID --> Q0{재실·신원 일치?}
  Q0 -- no --> UVS["UpdateVisitStatus (DB 기록) → 마지막 재방문"]
  UVS --> Q1
  Q0 -- yes --> VAL["처방/환자 검증<br/>GetPrescription /robot6/db/get_prescription"]
  VAL --> IV["웹 문진표 작성<br/>/intake → RTDB patients/intake"]
  IV --> Q1{남은 병실?}
  Q1 -- yes --> P0
  Q1 -- no --> R0["복귀 NavigateToPose(station)"]
  R0 --> D0["Dock /robot6/dock"] --> E0([도킹 완료])
```

### 5.2 시나리오 B — 간호사 추종 + 약품 OCR

```mermaid
flowchart TD
  B0([Station 도킹]) --> BU["Undock"]
  BU --> TR["간호사 추종 시작<br/>Trigger /robot6/start_tracking"]
  TR --> FOL["추종 주행<br/>tracker_node → /robot6/mode/round/cmd_vel"]
  FOL --> GATE{전방 장애물?<br/>lidar 0.30m / depth 0.20m}
  GATE -- yes --> STOP["safety_gate 전진 차단"] --> FOL
  GATE -- no --> ARR["호실 도착 (STANDBY)"]
  ARR --> SC["약품 OCR 검증<br/>웹 /ocr(GCP Vision) ↔ 처방 step"]
  SC --> Q2{투약 완료?}
  Q2 -- no --> SC
  Q2 -- yes --> BR["복귀 NavigateToPose(station)"]
  BR --> BD["Dock"] --> BE0([도킹 완료])
```

### 5.3 회진 풀스크린 모드 (웹 주도)

```mermaid
flowchart TD
  H0["홈 / '회진 모드' 배너 클릭"] --> CF{재확인}
  CF -- 확인 --> UD["docked면 undock<br/>pushMission(undock) + dock_status 대기"]
  UD --> RD["saveMode(start, round) → round 추종 시작"]
  RD --> OV["FollowOverlay 풀스크린 (SSE pose 구독)"]
  OV --> NP{"약품실/101호 1·2<br/>1m 근접?"}
  NP -- yes --> TXT["'OO에 도착' 표시 (로봇은 계속 추종)"]
  TXT --> OV
  NP -- no --> OV
  OV --> RB["'홈 위치로 복귀' 버튼"]
  RB --> RH["saveMode(stop,round) + goto(dock,dock_after) → 도킹 후 종료"]
```
````

- [ ] **Step 2: 검증**

Run: `cd /home/rokey/MediCart && python3 docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md`
Expected: `OK ...: 13 mermaid blocks 통과`

- [ ] **Step 3: 커밋**

```bash
cd /home/rokey/MediCart
git add docs/architecture/05_mermaid_architecture.md
git commit -m "docs(arch): §5 시나리오 플로우(A/B/회진)"
```

---

## Task 7: §6 인터페이스 레퍼런스 표 + 코드 재검증

**Files:**
- Modify: `docs/architecture/05_mermaid_architecture.md` (append)

- [ ] **Step 1: §6 섹션 추가**

파일 끝에 추가:
```markdown
## 6. 인터페이스 레퍼런스

### 토픽
| 토픽 | 타입 | pub → sub |
| --- | --- | --- |
| `/robot6/mission_request` | std_msgs/String | db_node → mission_manager_node |
| `/robot6/mission_feedback` | std_msgs/String | mission_manager_node → db_node |
| `/robot6/mission_cancel` | std_msgs/String | db_node → mission_manager_node (선점) |
| `/robot6/cmd_vel` | geometry_msgs/Twist | mission_manager_node(단독) → Create3 |
| `/robot6/robot_mode` | std_msgs/String | mission_manager_node → 모니터 |
| `/robot6/mode/{mode}/set` | std_msgs/String (latched) | mode_arbiter → 모드노드 |
| `/robot6/mode/{mode}/cmd_vel` | geometry_msgs/Twist | 모드노드 → mode_arbiter |
| `/robot6/mode/{mode}/status` | std_msgs/String | 모드노드 → mode_arbiter |
| `/robot6/identify/start` | std_msgs/String | patrol_mode_node → identifier_node |
| `/robot6/patient_identified` | medi_interfaces/PatientIdentified | identifier_node → patrol_mode_node, display_bridge |
| `/nurse_tracker/target` | std_msgs/String | tracker_node → 시각화 |
| `/nurse_tracker/annotated_image` | sensor_msgs/Image | tracker_node → 시각화 |
| `/obstacle_detector/ground_cloud` | sensor_msgs/PointCloud2 | obstacle_node → RViz |
| `/obstacle_detector/ground_status` | std_msgs/String | obstacle_node → safety_gate |
| `/robot6/scan` | sensor_msgs/LaserScan | RPLIDAR → amcl/nav2/mission_manager |
| `/robot6/odom` · `/robot6/battery_state` · `/robot6/dock_status` | nav_msgs/Odometry · sensor_msgs/BatteryState · irobot_create_msgs/DockStatus | Create3 → 구독자 |
| `/robot6/amcl_pose` · `/robot6/map` | geometry_msgs/PoseWithCovarianceStamped · nav_msgs/OccupancyGrid | AMCL/map_server → Nav2 |
| `/robot6/oakd/rgb/*` · `/robot6/oakd/stereo/*` | sensor_msgs/Image·CompressedImage·CameraInfo | OAK-D → 인지 |

### 서비스
| 서비스 | 타입 | 서버 → 클라이언트 |
| --- | --- | --- |
| `/robot6/db/get_prescription` | medi_interfaces/GetPrescription | prescription_server → identifier_node |
| `/robot6/db/list_rooms` | medi_interfaces/ListRooms | rooms_server → patrol_mode_node |
| `/robot6/start_tracking` | std_srvs/Trigger | tracker_node ← mission_manager/웹 |

### 액션
| 액션 | 타입 | 서버 → 클라이언트 |
| --- | --- | --- |
| `/robot6/navigate_to_pose` | nav2_msgs/NavigateToPose | Nav2 bt_navigator ← nav_executor·patrol_mode·dashboard |
| `/robot6/dock` · `/robot6/undock` | irobot_create_msgs/action/Dock·Undock | Create3 ← nav_executor·mission_executor·dashboard |

### Firebase RTDB 경로
| 경로 | 용도 |
| --- | --- |
| `robot6/mission_pool` | 미션 큐(웹→로봇) + 상태(로봇→웹) — action·params·status·ts |
| `robot6/mission_status` · `robot6/mission_log` | db_node 하트비트 · 종료 아카이브 |
| `robot6/cmd` | 모드 명령(웹 publish_mode_cmd → db_node) |
| `patients/{pid}/{info,injections,intake,visits,vitals}` | 환자 데이터·문진·생체징후·약품 |
| `rooms` · `targets` | 병실 waypoint · goto 프리셋(ninety 좌표) |
| `intake_pending` · `display/current_patient` · `ocr/latest` · `{src}/alerts` · `telemetry` | 환자 자가문진·디스플레이·OCR·알림·텔레메트리 |

> **medi_interfaces 선정의·미결선**(integration_todoList 참고): srv `GetOcrResult·ScanMedicine·VerifyMedicine·ScanPatient·StartMedication·StartPatrol·MoveHome·UpdateVisitStatus`, msg `MedicineInfo·PatientInfo·RobotState·TargetBBox`.
> 빌트인(외부): `depthai_ros_driver`(OAK-D) · `rplidar_ros` · `turtlebot4_node` · `nav2_*` · `irobot_create_msgs`.
```

- [ ] **Step 2: 표의 인터페이스 이름 코드 재검증**

Run:
```bash
cd /home/rokey/MediCart/medicart_ws/src
for n in mission_request mission_feedback mission_cancel robot_mode identify/start patient_identified start_tracking get_prescription list_rooms navigate_to_pose nurse_tracker/annotated_image obstacle_detector/ground; do
  c=$(grep -rE "['\"][^'\"]*${n}[^'\"]*['\"]" --include=*.py . 2>/dev/null | grep -v __pycache__ | head -1)
  [ -n "$c" ] && echo "OK  $n" || echo "MISSING  $n"
done
```
Expected: 모든 줄 `OK ...` (MISSING 0). MISSING 있으면 해당 표 행을 코드 실제 이름으로 수정.

- [ ] **Step 3: 전체 파일 최종 mermaid 검증**

Run: `cd /home/rokey/MediCart && python3 docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md`
Expected: `OK ...: 13 mermaid blocks 통과`

- [ ] **Step 4: 커밋**

```bash
cd /home/rokey/MediCart
git add docs/architecture/05_mermaid_architecture.md
git commit -m "docs(arch): §6 인터페이스 표 + 코드 재검증"
```

---

## Task 8: 최종 점검 (오늘 변경분 반영 확인 + 영향도)

**Files:** (검사만, 변경 없음)

- [ ] **Step 1: 오늘 변경분 누락 0 확인**

Run:
```bash
cd /home/rokey/MediCart
for k in mission_cancel "START_TIMEOUT\|15s\|무제한" "preempt\|선점\|드롭" "irobot_create_msgs/action/Dock"; do
  grep -qE "$k" docs/architecture/05_mermaid_architecture.md && echo "OK  $k" || echo "MISSING  $k"
done
```
Expected: 모두 `OK`.

- [ ] **Step 2: 영향도 — 다른 architecture 문서·코드 무변경 확인**

Run: `cd /home/rokey/MediCart && git status --porcelain docs/architecture | grep -v "05_mermaid_architecture.md\|check_mermaid.py" || echo "다른 파일 변경 없음(OK)"`
Expected: `다른 파일 변경 없음(OK)`

- [ ] **Step 3: 최종 검증 + (필요 시) finishing-a-development-branch**

Run: `cd /home/rokey/MediCart && python3 docs/architecture/check_mermaid.py docs/architecture/05_mermaid_architecture.md`
Expected: `OK ...: 13 mermaid blocks 통과`

---

## Self-Review (작성자 체크)

**Spec coverage:** §1 마스터(Task2) · §2 컴퓨트/네트워크/HW(Task3) · §3 노드그래프+타입+mission_cancel(Task4) · §4 상태머신 신규동작(Task5) · §5 시나리오 A/B/회진(Task6) · §6 인터페이스표(Task7) · 권위 진실값(헤더+Task5/7에 인코딩) · 검증(check_mermaid + grep, Task1/7/8) · 영향도(Task8). 모든 스펙 항목에 태스크 대응.

**Placeholder scan:** 모든 mermaid·표가 완성 코드. "TBD/추후" 없음.

**Type consistency:** dock/undock=`irobot_create_msgs/action/Dock·Undock`, mission_cancel=`std_msgs/String`, START_TIMEOUT 15s, 우선순위 수치, NON_PREEMPTIBLE 목록이 §3/§4/§6 전반에서 동일하게 사용됨.

**검증 도구 한계 명시:** `check_mermaid.py`는 완전 파서가 아니라 구조 린터(펜스/타입/균형). 더 강한 검증이 필요하면 `npx -y @mermaid-js/mermaid-cli`(네트워크·chromium 필요)로 렌더 가능 — 선택사항.
