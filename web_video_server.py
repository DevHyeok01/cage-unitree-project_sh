import cv2
import time
import json
import numpy as np
from flask import Flask, Response, render_template, request, jsonify
from multiprocessing import Queue
from webrtc_producer import start_webrtc, send_command, ensure_normal_mode_once
import threading
from ultralytics import YOLO  # YOLO 모델 임포트
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__, template_folder='templates')
frame_queue = Queue(maxsize=10)
command_queue = Queue(maxsize=10)

# YOLO 모델 로드
yolo_model = YOLO('project_CAGE/templates/yolo11n.pt')  # 모델 파일 경로

# LiDAR 관련 전역 변수
lidar_active = False
lidar_data = {
    'positions': [],
    'point_count': 0,
    'timestamp': time.time()
}


# WebRTC 프레임 수신 시작 (명령 큐도 전달)
start_webrtc(frame_queue, command_queue)

def generate():
    last_detect_time = 0
    last_boxes = []
    while True:
        if not frame_queue.empty():
            img = frame_queue.get()
            now = time.time()
            # 1초에 한 번만 YOLO 추론
            if now - last_detect_time > 1.0:
                results = yolo_model(img)
                last_boxes = []
                for result in results:
                    boxes = result.boxes
                    for box in boxes:
                        cls = int(box.cls[0])
                        label = yolo_model.names[cls]
                        if label == "person":
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            last_boxes.append((x1, y1, x2, y2))
                last_detect_time = now
            # 이전 결과(박스)만 영상에 표시
            for (x1, y1, x2, y2) in last_boxes:
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(img, "person", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)
            ret, jpeg = cv2.imencode('.jpg', img)
            if not ret:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        else:
            time.sleep(0.01)

@app.route('/video_feed')
def video_feed():
    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/move', methods=['POST'])
def move():
    data = request.get_json()
    direction = data.get('direction')
    send_command(command_queue, direction)
    return jsonify({'status': 'ok', 'direction': direction})

@app.route('/joystick', methods=['POST'])
def joystick():
    data = request.get_json()
    x = float(data.get('x', 0))
    z = float(data.get('z', 0))
    send_command(command_queue, ('joystick', x, z))
    return jsonify({'status': 'ok'})

@app.route('/start_control', methods=['POST'])
def start_control():
    try:
        command_queue.put("start_control")
        return jsonify({'status': 'success', 'message': 'Remote control started'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/lidar_data', methods=['GET'])
def get_lidar_data():
    """LiDAR 포인트 클라우드 데이터 반환"""
    global lidar_data, lidar_active
    
    if not lidar_active:
        return jsonify({
            'positions': [],
            'point_count': 0,
            'timestamp': time.time()
        })
    
    # 모의 LiDAR 데이터 생성 (실제 LiDAR 연결 시 실제 데이터로 대체)
    current_time = time.time()
    positions = []
    
    # 원형 패턴의 포인트 클라우드 생성
    for i in range(360):
        angle = np.radians(i)
        distance = 2.0 + 0.5 * np.sin(current_time + angle * 4)  # 시간에 따라 변화하는 거리
        x = distance * np.cos(angle)
        y = distance * np.sin(angle)
        z = 0.1 * np.sin(current_time * 2 + angle * 8)  # 약간의 높이 변화
        positions.extend([x, y, z])
    
    # 추가 랜덤 포인트들
    for _ in range(100):
        x = (np.random.random() - 0.5) * 6
        y = (np.random.random() - 0.5) * 6
        z = np.random.random() * 0.5
        positions.extend([x, y, z])
    
    lidar_data = {
        'positions': positions,
        'point_count': len(positions) // 3,
        'timestamp': current_time
    }
    
    return jsonify(lidar_data)

@app.route('/toggle_lidar', methods=['POST'])
def toggle_lidar():
    """LiDAR 활성화/비활성화 토글"""
    global lidar_active
    
    try:
        lidar_active = not lidar_active
        status = "active" if lidar_active else "inactive"
        return jsonify({
            'status': 'success',
            'lidar_active': lidar_active,
            'message': f'LiDAR is now {status}'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })
    

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5010, debug=False)


'''
@misc{lin2015microsoft,
      title={Microsoft COCO: Common Objects in Context},
      author={Tsung-Yi Lin and Michael Maire and Serge Belongie and Lubomir Bourdev and Ross Girshick and James Hays and Pietro Perona and Deva Ramanan and C. Lawrence Zitnick and Piotr Dollár},
      year={2015},
      eprint={1405.0312},
      archivePrefix={arXiv},
      primaryClass={cs.CV}
}
'''
