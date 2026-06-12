#!/usr/bin/env python3
"""camera_bridge — nurse_tracking 탐지 영상(annotated RGB) + depth 컬러맵을 RTDB로 저fps 송출.

웹(무-ROS)이 대시보드에서 '어떻게 탐지되는지' 보도록, 로봇측에서 프레임을 다운스케일 JPEG→base64
로 RTDB {ns}/camera 에 ~camera_fps 로 적는다. RTDB 부하 절감 위해 **웹 패널이 열려 요청(on)** 일
때만 구독·인코딩한다({ns}/camera/request {on, ts} 하트비트, ts 신선할 때만 활성).

구독(요청 on일 때만 동적 생성 → 평소엔 tracker annotated lazy off):
  · /nurse_tracker/annotated_image (raw Image bgr8) — tracker 가 그린 탐지 오버레이(글로벌 토픽).
  · /{ns}/oakd/stereo/image_raw/compressedDepth — depth(컬러맵용).
  · /{ns}/oakd/rgb/image_raw/compressed — tracker 미가동 시 원본 RGB 폴백.
"""
import base64
import os
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image

from db_bridge.firebase_client import FirebaseClient

_QOS_SENSOR = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
_CDEPTH_HEADER_BYTES = 12          # compressed_depth_image_transport ConfigHeader(12B) 후 PNG
_DEPTH_NEAR_MM = 300
_DEPTH_FAR_MM = 4000


def _now_ms():
    return int(time.time() * 1000)


class CameraBridge(Node):
    """탐지 RGB + depth 컬러맵 → RTDB(JPEG base64) 저fps 브리지(요청 게이트)."""

    def __init__(self):
        super().__init__('camera_bridge')
        self.declare_parameter('namespace', os.environ.get('ROBOT_NAMESPACE', 'robot6'))
        self.declare_parameter('fb_cred', os.environ.get('FB_CRED', ''))
        self.declare_parameter('fb_db_url', os.environ.get('FB_DB_URL', ''))
        self.declare_parameter('camera_fps', 3.0)
        self.declare_parameter('width', 320)
        self.declare_parameter('jpeg_quality', 60)
        self.declare_parameter('request_ttl', 6.0)

        self.ns = str(self.get_parameter('namespace').value).strip('/')
        cred = str(self.get_parameter('fb_cred').value)
        url = str(self.get_parameter('fb_db_url').value)
        self._fps = max(1.0, float(self.get_parameter('camera_fps').value))
        self._w = int(self.get_parameter('width').value)
        self._jq = int(self.get_parameter('jpeg_quality').value)
        self._ttl_ms = float(self.get_parameter('request_ttl').value) * 1000.0

        self.get_logger().info(f'[camera_bridge] RTDB 연결 ns=/{self.ns}')
        self._fb = FirebaseClient(cred, url, logger=self.get_logger())

        self._annotated = None     # 최신 bgr 프레임(탐지 오버레이)
        self._rgb = None           # 최신 bgr 프레임(원본 폴백)
        self._depth = None         # 최신 depth(16UC1 mm)
        self._subs = []            # 동적 구독 핸들
        self._active = False
        self._req_on = False
        self._req_ts = 0

        self._req_path = f'{self.ns}/camera/request'
        self._fb.listen(self._req_path, self._on_request)
        self.create_timer(1.0 / self._fps, self._tick)
        self.get_logger().info(
            f'[camera_bridge] {self.ns} 카메라 송출 준비({self._fps:.0f}fps, {self._w}px, '
            f'요청 게이트 {self._req_path})')

    # ── 요청 게이트(웹 패널 열림 하트비트) ────────────────────────────────
    def _on_request(self, event):
        try:
            req = self._fb.read(self._req_path)
        except Exception as exc:                       # noqa: BLE001
            self.get_logger().warn(f'[camera_bridge] request 읽기 오류: {exc}')
            return
        if isinstance(req, dict):
            self._req_on = bool(req.get('on'))
            self._req_ts = int(req.get('ts', 0))

    def _request_fresh(self):
        return self._req_on and (_now_ms() - self._req_ts) < self._ttl_ms

    # ── 동적 구독(활성 시에만 — 평소 tracker annotated lazy off) ──────────
    def _activate(self):
        if self._subs:
            return
        self._subs = [
            self.create_subscription(Image, '/nurse_tracker/annotated_image',
                                     self._on_annotated, _QOS_SENSOR),
            self.create_subscription(CompressedImage,
                                     f'/{self.ns}/oakd/stereo/image_raw/compressedDepth',
                                     self._on_depth, _QOS_SENSOR),
            self.create_subscription(CompressedImage,
                                     f'/{self.ns}/oakd/rgb/image_raw/compressed',
                                     self._on_rgb, _QOS_SENSOR),
        ]
        self._active = True
        self.get_logger().info('[camera_bridge] ▶ 활성(웹 패널 열림) — 구독 생성')

    def _deactivate(self):
        if not self._subs:
            return
        for s in self._subs:
            self.destroy_subscription(s)
        self._subs = []
        self._annotated = self._rgb = self._depth = None
        self._active = False
        self.get_logger().info('[camera_bridge] ■ 비활성(요청 없음) — 구독 해제')

    # ── 프레임 캐시 ──────────────────────────────────────────────────────
    def _on_annotated(self, msg):
        try:
            self._annotated = np.frombuffer(bytes(msg.data), np.uint8).reshape(
                msg.height, msg.width, 3)
        except Exception:                              # noqa: BLE001
            pass

    def _on_rgb(self, msg):
        img = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            self._rgb = img

    def _on_depth(self, msg):
        try:
            png = np.frombuffer(bytes(msg.data)[_CDEPTH_HEADER_BYTES:], np.uint8)
            d = cv2.imdecode(png, cv2.IMREAD_UNCHANGED)
            if d is not None:
                self._depth = d
        except Exception:                              # noqa: BLE001
            pass

    # ── 인코딩 헬퍼 ──────────────────────────────────────────────────────
    def _to_jpeg_b64(self, bgr):
        h, w = bgr.shape[:2]
        if w != self._w:
            bgr = cv2.resize(bgr, (self._w, max(1, int(h * self._w / w))))
        ok, buf = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, self._jq])
        if not ok:
            return None, 0, 0
        return base64.b64encode(buf).decode('ascii'), bgr.shape[1], bgr.shape[0]

    def _depth_colormap(self, depth):
        d = depth.astype(np.float32)
        norm = np.clip(d, _DEPTH_NEAR_MM, _DEPTH_FAR_MM)
        scaled = ((norm - _DEPTH_NEAR_MM) / (_DEPTH_FAR_MM - _DEPTH_NEAR_MM) * 255.0).astype(np.uint8)
        cm = cv2.applyColorMap(scaled, cv2.COLORMAP_JET)
        cm[depth == 0] = (0, 0, 0)                     # 무효 depth 는 검정
        return cm

    # ── 주기 송출 ────────────────────────────────────────────────────────
    def _tick(self):
        if self._request_fresh():
            self._activate()
        else:
            self._deactivate()
            return

        payload = {'ts': _now_ms()}
        rgb_src = self._annotated if self._annotated is not None else self._rgb
        if rgb_src is not None:
            b64, w, h = self._to_jpeg_b64(rgb_src)
            if b64:
                payload.update(rgb=b64, w=w, h=h,
                               src=('annotated' if self._annotated is not None else 'raw'))
        if self._depth is not None:
            b64, _, _ = self._to_jpeg_b64(self._depth_colormap(self._depth))
            if b64:
                payload['depth'] = b64
        if 'rgb' not in payload and 'depth' not in payload:
            return                                     # 아직 프레임 없음
        try:
            self._fb.update(f'{self.ns}/camera', payload)
        except Exception as exc:                       # noqa: BLE001
            self.get_logger().warn(f'[camera_bridge] camera 쓰기 실패: {exc}')


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = CameraBridge()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
