import cv2
from flask import Flask, Response

# Inicializar Flask
app = Flask(__name__)

# Ruta RTSP (la misma que en camnew.py)
rtsp_url = "rtsp://admin:abcd1234..@181.236.158.144:554/Streaming/Channels/101"

# Captura de video
camera = cv2.VideoCapture(rtsp_url)

def generate_original_frames():
    """Genera frames originales sin procesar"""
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            # Codificar el frame como JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


def generate_processed_frames():
    """Genera frames procesados (puedes añadir más procesamiento aquí)"""
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
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
    app.run(host='0.0.0.0', port=5000, debug=False)
