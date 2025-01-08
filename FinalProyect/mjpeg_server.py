import cv2
from flask import Flask, Response
import time

# Inicializar Flask
app = Flask(__name__)

# Ruta RTSP (la misma que en camnew.py)
rtsp_url = "rtsp://admin:abcd1234..@161.10.84.55:554/Streaming/Channels/101"

# Captura de video
camera = cv2.VideoCapture(rtsp_url)
camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Ajustar a 1 frame para minimizar retraso
camera.set(cv2.CAP_PROP_FPS, 10)        # Limitar los FPS a 10
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Reducir resolución
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)


def reconnect_camera():
    """Intenta reconectar la cámara en caso de fallo"""
    global camera
    print("Reconectando a la cámara...")
    camera.release()  # Libera la conexión existente
    time.sleep(2)  # Espera unos segundos antes de intentar reconectar
    camera = cv2.VideoCapture(rtsp_url)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    camera.set(cv2.CAP_PROP_FPS, 10)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)


def generate_original_frames():
    """Genera frames originales con reconexión automática"""
    global camera
    while True:
        if not camera.isOpened():
            reconnect_camera()

        success, frame = camera.read()
        if not success:
            print("Error leyendo el frame, intentando reconectar...")
            reconnect_camera()
            continue

        # Codificar el frame como JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


def generate_processed_frames():
    """Genera frames procesados (puedes añadir más procesamiento aquí)"""
    global camera
    while True:
        if not camera.isOpened():
            reconnect_camera()

        success, frame = camera.read()
        if not success:
            print("Error leyendo el frame, intentando reconectar...")
            reconnect_camera()
            continue

        # Procesar el frame (ejemplo: dibujar rectángulos o texto en el frame)
        cv2.putText(frame, "Processed Frame", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/video_feed')
def video_feed():
    """Servir el feed original"""
    return Response(generate_original_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/processed_feed')
def processed_feed():
    """Servir el feed procesado"""
    return Response(generate_processed_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=False)
