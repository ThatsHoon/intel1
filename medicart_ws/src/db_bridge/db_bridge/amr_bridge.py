#!/usr/bin/env python3
"""amr_bridge — AMR 원시 토픽 → RTDB 1Hz 텔레메트리 + /rosout 로그(WARN+) 브리지.

웹(PC3)은 ROS 없이 RTDB만 읽으므로, 로봇측 토픽 값을 RTDB {ns} 노드에 주기적으로 적어줘야
지도/콘솔이 pose·vel·battery·dock·scan 을 렌더한다(web fb_read.topics_to_snapshot 계약과 1:1).
또한 /rosout(WARN/ERROR/FATAL)을 모아 {ns}/logs(최신 500, 최신순)로 적어 관리자 콘솔이 실시간 표시.

설계
  · 토픽별 최신값만 캐시(웹 평탄 스키마 모양으로 변환) → 1Hz 타이머가 {ns} 노드를 **update**.
    update 라서 mission_pool/cmd/mission_status 등 다른 키는 보존된다(set 금지).
  · 로그는 deque(500) 버퍼 → 변동 있을 때만 {ns}/logs 에 최신순 set(과도한 쓰기 방지).
  · scan 은 페이로드 절감 위해 ~120점 다운샘플, inf/nan 은 null(web ranges: number|null).
  · /rosout 은 전역 토픽이라 공유 discovery 에서 타 로봇 로그가 섞일 수 있어 peer_namespace 로 제외.
"""
import math
import os
import re
import subprocess
import threading
import time
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from geometry_msgs.msg import PoseWithCovarianceStamped
from irobot_create_msgs.msg import DockStatus
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import Log
from sensor_msgs.msg import BatteryState, Imu, LaserScan
from std_msgs.msg import String

from db_bridge.firebase_client import FirebaseClient

LOG_LEVELS = {10: 'DEBUG', 20: 'INFO', 30: 'WARN', 40: 'ERROR', 50: 'FATAL'}
SCAN_MAX_POINTS = 120
LOG_CAP = 500
HEALTH_PERIOD = 2.0          # health(ping/create3/turtlebot4) 갱신 주기(초)
FRESH_S = 4.0                # 토픽 신선도 임계(초) — 이내면 alive
_DEFAULT_IPS = {'robot6': '192.168.109.106', 'robot3': '192.168.109.103'}


def _yaw_from_quat(x, y, z, w):
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def _now_ms():
    return int(time.time() * 1000)


class AmrBridge(Node):
    """원시 토픽 → RTDB 1Hz 텔레메트리 + /rosout 로그 브리지."""

    def __init__(self):
        super().__init__('amr_bridge')
        self.declare_parameter('namespace', os.environ.get('ROBOT_NAMESPACE', 'robot6'))
        self.declare_parameter('fb_cred', os.environ.get('FB_CRED', ''))
        self.declare_parameter('fb_db_url', os.environ.get('FB_DB_URL', ''))
        self.declare_parameter('peer_namespace', os.environ.get('PEER_NAMESPACE', ''))
        self.declare_parameter('rate_hz', 1.0)
        self.declare_parameter('log_min_level', 30)   # WARN 이상
        self.declare_parameter('robot_ip', '')        # 미설정 시 ns 로 추정

        self.ns = str(self.get_parameter('namespace').value).strip('/')
        cred = str(self.get_parameter('fb_cred').value)
        url = str(self.get_parameter('fb_db_url').value)
        self._peer = str(self.get_parameter('peer_namespace').value).strip('/')
        self._log_min = int(self.get_parameter('log_min_level').value)
        rate = max(0.2, float(self.get_parameter('rate_hz').value))
        self._robot_ip = str(self.get_parameter('robot_ip').value) or _DEFAULT_IPS.get(self.ns, '')

        self.get_logger().info(f'[amr_bridge] RTDB 연결 ns=/{self.ns} url={url}')
        self._fb = FirebaseClient(cred, url, logger=self.get_logger())

        self._snap = {}                       # 웹 평탄 스키마 토픽키 → 값
        self._logs = deque(maxlen=LOG_CAP)
        self._logs_dirty = False
        self._last_create3 = 0.0              # dock_status/odom 최신 수신(monotonic)
        self._last_tb4 = 0.0                  # scan(rplidar=turtlebot4.service) 최신 수신

        s = qos_profile_sensor_data
        self.create_subscription(PoseWithCovarianceStamped, f'/{self.ns}/amcl_pose', self._on_pose, 10)
        self.create_subscription(Odometry, f'/{self.ns}/odom', self._on_odom, s)
        self.create_subscription(BatteryState, f'/{self.ns}/battery_state', self._on_batt, s)
        self.create_subscription(DockStatus, f'/{self.ns}/dock_status', self._on_dock, s)
        self.create_subscription(Imu, f'/{self.ns}/imu', self._on_imu, s)
        self.create_subscription(LaserScan, f'/{self.ns}/scan', self._on_scan, s)
        self.create_subscription(String, f'/{self.ns}/robot_mode', self._on_mode, 10)
        self.create_subscription(Log, '/rosout', self._on_rosout, 10)

        self.create_timer(1.0 / rate, self._flush)

        # health(ping/create3/turtlebot4)는 블로킹(ping) 이라 별도 데몬 스레드에서 2s 비동기.
        # ROS executor 를 막지 않도록 절대 콜백/타이머에서 ping 하지 않는다.
        self._stop = threading.Event()
        self._health_thr = threading.Thread(target=self._health_loop, daemon=True)
        self._health_thr.start()

        self.get_logger().info(
            f'[amr_bridge] {self.ns} 텔레메트리 {rate:.0f}Hz + /rosout(>= '
            f'{LOG_LEVELS.get(self._log_min, self._log_min)}) + health 2s(ping {self._robot_ip}) '
            f'→ RTDB {self.ns}/{{telemetry,logs,health}}')

    # ── 토픽 캐시(웹 평탄 스키마 모양) ──────────────────────────────────────
    def _on_pose(self, m):
        p = m.pose.pose
        self._snap['amcl_pose'] = {
            'x': round(p.position.x, 4), 'y': round(p.position.y, 4),
            'yaw': round(_yaw_from_quat(p.orientation.x, p.orientation.y,
                                        p.orientation.z, p.orientation.w), 4)}

    def _on_odom(self, m):
        self._snap['odom'] = {'lin': round(m.twist.twist.linear.x, 4),
                              'ang': round(m.twist.twist.angular.z, 4)}
        self._last_create3 = time.monotonic()      # odom = Create3 본체

    def _on_batt(self, m):
        pct = m.percentage * 100.0 if m.percentage <= 1.0 else m.percentage
        self._snap['battery_state'] = {'pct': round(pct, 1), 'voltage': round(m.voltage, 2)}

    def _on_dock(self, m):
        self._snap['dock_status'] = {'is_docked': bool(m.is_docked)}
        self._last_create3 = time.monotonic()      # dock_status = Create3 본체

    def _on_imu(self, m):
        self._snap['imu'] = {'yaw_rate': round(m.angular_velocity.z, 4)}

    def _on_scan(self, m):
        self._last_tb4 = time.monotonic()          # rplidar scan = turtlebot4.service 생존
        n = len(m.ranges)
        step = max(1, n // SCAN_MAX_POINTS)
        ranges = []
        for i in range(0, n, step):
            r = m.ranges[i]
            ranges.append(round(float(r), 3) if math.isfinite(r) and r > 0.0 else None)
        self._snap['scan'] = {'angle_min': round(m.angle_min, 4),
                              'angle_inc': round(m.angle_increment * step, 5),
                              'range_max': round(m.range_max, 2), 'ranges': ranges}

    def _on_mode(self, m):
        self._snap['robot_mode'] = m.data

    def _on_rosout(self, m):
        if m.level < self._log_min:
            return
        if self._peer and self._peer in m.name:
            return                            # 공유 discovery — 타 로봇 노드 로그 제외
        self._logs.append({'ts': _now_ms(), 'node': m.name,
                           'level': LOG_LEVELS.get(m.level, str(m.level)),
                           'msg': m.msg[:300]})
        self._logs_dirty = True

    # ── 1Hz flush(텔레메트리 update + 로그 set) ────────────────────────────
    def _flush(self):
        payload = dict(self._snap)
        payload['robot_mode'] = self._snap.get('robot_mode', 'idle')
        payload['online'] = True
        payload['stamp'] = _now_ms()
        try:
            self._fb.update(self.ns, payload)   # {ns} 의 토픽 키만 갱신(다른 키 보존)
        except Exception as exc:                # noqa: BLE001 (브리지 안정성)
            self.get_logger().warn(f'[amr_bridge] telemetry 쓰기 실패: {exc}')

        if self._logs_dirty:
            try:
                self._fb.write(f'{self.ns}/logs', list(self._logs)[::-1])  # 최신순
                self._logs_dirty = False
            except Exception as exc:            # noqa: BLE001
                self.get_logger().warn(f'[amr_bridge] logs 쓰기 실패: {exc}')


    # ── health 데몬(2s 비동기 — ping 블로킹을 ROS executor 밖에서) ─────────
    def _ping(self, ip):
        """ip 1회 ping → (ok, rtt_ms|None). 블로킹이라 health 스레드에서만 호출."""
        if not ip:
            return False, None
        try:
            r = subprocess.run(['ping', '-c', '1', '-W', '2', ip],
                               capture_output=True, text=True, timeout=4)
        except Exception:                              # noqa: BLE001
            return False, None
        if r.returncode != 0:
            return False, None
        m = re.search(r'time=([\d.]+)', r.stdout)
        return True, (round(float(m.group(1)), 1) if m else None)

    def _health_loop(self):
        while rclpy.ok() and not self._stop.is_set():
            ok, ms = self._ping(self._robot_ip)
            now = time.monotonic()
            health = {
                'ping_ok': ok,
                'ping_ms': ms,
                'create3': bool(self._last_create3) and (now - self._last_create3) < FRESH_S,
                'turtlebot4': bool(self._last_tb4) and (now - self._last_tb4) < FRESH_S,
                'ip': self._robot_ip,
                'ts': _now_ms(),
            }
            try:
                self._fb.update(f'{self.ns}/health', health)
            except Exception as exc:                   # noqa: BLE001
                self.get_logger().warn(f'[amr_bridge] health 쓰기 실패: {exc}')
            self._stop.wait(HEALTH_PERIOD)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = AmrBridge()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node._stop.set()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
