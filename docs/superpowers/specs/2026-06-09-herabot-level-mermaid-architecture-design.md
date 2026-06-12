# HERA급 Mermaid 아키텍처 문서 개편 — 설계(Spec)

> 작성 2026-06-09 · 통합 브랜치(`integration`) 기준 · namespace 기본 `robot6`.
> 참조 수준: `~/Downloads/별첨.SystemArchitectureDiagram_HERABot.pdf` (HERABot 단일 초대형 도면).

## 목표

`docs/architecture/05_mermaid_architecture.md` 를 **HERA 수준**(① 모든 엣지에 `<type>`+값 ② SW 스택 컨테이너 ③ HW 인벤토리 ④ 모드/미션 상태머신 ⑤ 네트워크 레이어 ⑥ 결정 기준 명시)으로 전면 재작성한다. 동시에 오늘 변경된 미션 오케스트레이션(`mission_cancel`·우선순위 선점·15s 시작워치독/무제한 완료)을 정확히 반영한다.

## 결정 사항(확정)

- **구조**: 마스터 오버뷰 1장(HERA식 전체 배치) + 디테일 다이어그램 세트.
- **포함 범위**: 전부 — ROS 노드/토픽(타입·값) + turtlebot4 SW 스택 + HW 인벤토리 + FastDDS Discovery/네트워크 + 웹 스택.
- **로봇 표현**: robot6 대표 1대로 그리고 robot3 동일구조임을 주석.
- **대상 파일**: 기존 `docs/architecture/05_mermaid_architecture.md` 업데이트(전면 재작성). 다른 문서는 손대지 않음.

## 문서 구성(섹션 = 다이어그램)

### §1 마스터 오버뷰 (graph TD, 1장)
3 PC(PC1=robot3 전담, PC2=robot6 전담, PC3=웹) + robot6(turtlebot4) 컨테이너. 중앙에 Firebase RTDB(크로스-PC 버스)와 FastDDS Discovery Server(:11811, DOMAIN 6). 요약 엣지만: `mission_request`/`mission_feedback`/`mission_cancel`, telemetry, `navigate_to_pose`, `mode/*`. 각 컨테이너에 역할+핵심 스택 1줄. robot3은 "동일구조" 주석.

### §2 컴퓨트 & 네트워크 레이아웃 (graph TB)
HERA의 PC/HW 블록 대응. subgraph 별:
- **PC1(robot3)·PC2(robot6)**: Ubuntu 22.04 LTS · ROS2 Humble · FastDDS Discovery Server · RViz2(시각화 `/scan /map /tf /odom /image_raw`; Set Goal Pose→Nav2; Set Initial Pose→AMCL) · `loc6`(AMCL, bond_timeout 10s 패치) · `nav6`(Nav2, bond 패치) · 앱 패키지(db_bridge·mission_manager·nurse_tracker·obstacle_detector).
- **robot6(turtlebot4, RPi4B)**: turtlebot4_bringup(robot_state_publisher→`/robot_description`,`/tf`,`/tf_static` · rplidar_ros→`/scan` · depthai_ros_driver→`/oakd/rgb`,`/oakd/stereo`,`/camera_info` · diagnostics→`/battery_state` · HMI: 버튼/LED/오디오) · turtlebot4_navigation(AMCL · controller_server · planner_server · bt_navigator · map_server).
- **HW 인벤토리**: iRobot Create3 · Raspberry Pi 4B · RPLIDAR A1M8 · OAK-D-Pro · 배터리 · Status LED(MTR/COMM/WiFi/Battery/Power).
- **PC3(웹)**: Next.js :3000 · Flask :5000 · cloudflared 터널 (ROS 노드 없음, RTDB 읽기/쓰기만).
- **네트워크 푸터**: ROS2 Humble · WiFi6 AP · Gigabit Ethernet Switch · cloudflared(외부 접속).

### §3 ROS 노드 그래프 (graph LR, robot6, 타입 명시 통합본)
노드 전체와 **모든 엣지에 `<type>`+값**:
db_node · mission_manager_node · prescription_server · rooms_server · display_bridge · patrol_mode_node(시나리오A) · identifier_node(시나리오A) · tracker_node(시나리오B) · obstacle_node · Nav2(bt_navigator/controller/planner) · AMCL · map_server · Create3 · OAK-D · RPLIDAR.
(기존 §3.1~3.6 per-feature 다이어그램은 이 통합본 + 기능별 분해로 유지하되 전 엣지 타입화.)

### §4 상태머신 (stateDiagram-v2)
- **§4.1 미션 라이프사이클(신규 동작)**: `pending → sent →(accepted/running 미수신 시 15s 워치독)→ accepted → running(완료 타임아웃 없음 = 무제한) → done|failed`. 실행 중 **더 높은 우선순위 pending 도착 → preempted(현재 폐기·드롭)** 후 상위 시작. `dock/undock/ros_restart/reboot/shutdown/patrol_mission` 은 **비선점(NON_PREEMPTIBLE)**. nav_executor는 create3(undock/dock) 진행 중 cancel을 goal 취소 없이 안전 처리.
- **§4.2 모드 중재**: 우선순위 `intake(문진)5 > round(회진)4 > errand(지시)3 > guide(가이드)2 > patrol(순찰)1`(운영자 `goto`7·시스템 9는 별도), 선점/복귀 + status 워치독(무응답 lost abort) + safety_gate(전방 lidar 0.30m / depth 0.20m, 전진만 차단).

### §5 시나리오/기능 플로우 (flowchart TD, 결정 기준 포함)
- **§5.1 시나리오 A** 자율순찰+QR신원+문진: 도킹→Undock→ListRooms(병상 waypoint)→다음 병실 NavigateToPose→identifier_node 재실/신원확인→GetPrescription 검증→웹 문진표→{남은 병실? yes 반복 / no 복귀}→Dock. 부재/불일치 → UpdateVisitStatus.
- **§5.2 시나리오 B** 간호사 추종+약품 OCR: Undock→start_tracking→round 모드 추종(`/mode/round/cmd_vel`)→호실 도착(STANDBY)→약품 OCR 검증(웹 /ocr GCP Vision ↔ 처방 step, 반복)→{투약 완료? no 반복 / yes 복귀}→Dock. 전방 장애물 → safety_gate.
- **§5.3 회진 풀스크린(웹 주도)**: 홈 배너→재확인→(docked면 undock)→saveMode(start,round)→FollowOverlay 풀스크린(SSE pose)→{약품실/101호 1m 근접? → 'OO에 도착' 표시}→'홈 복귀' 버튼→saveMode(stop,round)+goto(dock,dock_after)→도킹 종료.

### §6 인터페이스 레퍼런스 표(확장 — 권위 목록)

**토픽**
| 토픽 | 타입 | pub → sub |
| --- | --- | --- |
| `/robot6/mission_request` | std_msgs/String | db_node → mission_manager_node |
| `/robot6/mission_feedback` | std_msgs/String | mission_manager_node → db_node |
| `/robot6/mission_cancel` | std_msgs/String | db_node → mission_manager_node (선점) |
| `/robot6/cmd_vel` | geometry_msgs/Twist | mission_manager_node(단독) → Create3 |
| `/robot6/robot_mode` | std_msgs/String | mission_manager_node → 모니터/웹 |
| `/robot6/mode/{mode}/set` | std_msgs/String (latched) | mode_arbiter → 모드노드 |
| `/robot6/mode/{mode}/cmd_vel` | geometry_msgs/Twist | 모드노드 → mode_arbiter |
| `/robot6/mode/{mode}/status` | std_msgs/String | 모드노드 → mode_arbiter |
| `/robot6/identify/start` | std_msgs/String | patrol_mode_node → identifier_node |
| `/robot6/patient_identified` | medi_interfaces/PatientIdentified | identifier_node → patrol_mode_node, display_bridge |
| `/nurse_tracker/target` · `/nurse_tracker/annotated_image` | std_msgs/String · sensor_msgs/Image | tracker_node → 시각화/디버그 |
| `/obstacle_detector/ground_cloud` · `/obstacle_detector/ground_status` | sensor_msgs/PointCloud2 · std_msgs/String | obstacle_node → RViz / safety_gate |
| `/robot6/scan` | sensor_msgs/LaserScan | RPLIDAR → amcl/nav2/mission_manager |
| `/robot6/odom` · `/robot6/battery_state` · `/robot6/dock_status` | nav_msgs/Odometry · sensor_msgs/BatteryState · irobot_create_msgs/DockStatus | Create3 → 구독자 |
| `/robot6/amcl_pose` · `/robot6/map` | geometry_msgs/PoseWithCovarianceStamped · nav_msgs/OccupancyGrid | AMCL/map_server → Nav2 |
| `/robot6/oakd/rgb/image_raw[/compressed]` · `/robot6/oakd/stereo/image_raw[/compressedDepth]` · `/robot6/oakd/*/camera_info` | sensor_msgs/Image·CompressedImage·CameraInfo | OAK-D → 인지 |

**서비스**
| 서비스 | 타입 | 서버 → 클라이언트 |
| --- | --- | --- |
| `/robot6/db/get_prescription` | medi_interfaces/GetPrescription | prescription_server → identifier_node |
| `/robot6/db/list_rooms` | medi_interfaces/ListRooms | rooms_server → patrol_mode_node |
| `/robot6/start_tracking` | std_srvs/Trigger | tracker_node ← mission_manager/웹 |

**액션**
| 액션 | 타입 | 서버 → 클라이언트 |
| --- | --- | --- |
| `/robot6/navigate_to_pose` | nav2_msgs/NavigateToPose | Nav2 bt_navigator ← nav_executor·patrol_mode·dashboard |
| `/robot6/dock` · `/robot6/undock` | irobot_create_msgs/action/Dock·Undock | Create3 ← nav_executor·mission_executor·dashboard |

**Firebase RTDB**
| 경로 | 용도 |
| --- | --- |
| `robot6/mission_pool` | 미션 큐(웹→로봇) + 상태(로봇→웹). 항목: action·params·status·ts |
| `robot6/mission_status` · `robot6/mission_log` | db_node 하트비트 · 종료 아카이브 |
| `robot6/cmd` | 모드 명령(웹 publish_mode_cmd → db_node) |
| `patients/{pid}/{info,injections,intake,visits,vitals}` | 환자 데이터·문진·생체징후·약품 |
| `rooms` · `targets` | 병실 waypoint · goto 프리셋(ninety 좌표) |
| `intake_pending` · `display/current_patient` · `ocr/latest` · `{src}/alerts` · `telemetry` | 환자 자가문진·디스플레이·OCR·알림·텔레메트리 |

> **medi_interfaces 선정의·미결선**(integration_todoList 참고): srv `GetOcrResult·ScanMedicine·VerifyMedicine·ScanPatient·StartMedication·StartPatrol·MoveHome·UpdateVisitStatus`, msg `MedicineInfo·PatientInfo·RobotState·TargetBBox`. 표/그래프에서 "정의됨·미결선"으로 구분 표기.

## 권위 사실(다이어그램에 인코딩할 진실값)

- dock/undock 액션 타입은 `irobot_create_msgs/action/Dock·Undock` (HERA의 `DockControl` 아님).
- 미션 시작 워치독 `START_TIMEOUT=15.0s`, 완료 타임아웃 없음.
- 우선순위표(`mission_queue.MISSION_PRIORITY`): shutdown/reboot/ros_restart 9 · goto 7 · dock/undock 6 · intake 5 · round 4 · errand 3 · guide 2 · patrol/patrol_mission 1, default 5.
- `NON_PREEMPTIBLE = dock, undock, ros_restart, reboot, shutdown, patrol_mission`.
- 미션 피드백 상태: `accepted → running → done | failed`, db_node 측 종료에 `preempted`(드롭)·`timeout` 추가.
- ninety 맵/좌표, 홈(dock) `x=-0.354229, y=-0.118972, yaw=-0.0042011`.

## 검증

- 각 mermaid 블록을 mermaid v10 파서로 구문 검사(로컬 `@mermaid-js/mermaid-cli` 또는 http.server 렌더, file:// 금지 — 빈 입력 false-error 회피).
- §6 표의 모든 토픽/서비스/액션 이름을 `medicart_ws/src` 코드 grep으로 재확인(존재·pub/sub 방향).
- 오늘 변경분(`mission_cancel`·우선순위·타임아웃) 누락 0 확인.
- 영향도: `05_mermaid_architecture.md` 단일 파일만 변경. 다른 architecture 문서·코드 무변경.

## 비목표(YAGNI)

- robot3 별도 대칭 다이어그램(주석으로 동일구조 명시로 충분).
- `db_node.py` docstring 갱신 등 코드 변경(별건).
- HTML(`diagrams/`) 재생성.
