import ffmpeg
import numpy as np
import cv2
import pytesseract
import threading
import queue
from collections import Counter
from flask import Flask, Response
import requests  # Importar requests para enviar datos al servidor

# Configuración de Flask
app = Flask(__name__)

# Configuración de Tesseract-OCR
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# URL RTSP de la cámara IP
rtsp_url = "rtsp://admin:abcd1234..@181.236.158.144:554/Streaming/Channels/101"

# Ruta completa al archivo ejecutable de FFmpeg
ffmpeg_path = r"C:\ffmpeg\ffmpeg.exe"

# Configura el tamaño de la ventana y la resolución
width, height = 1280, 720
roi_x, roi_y, roi_w, roi_h = 400, 200, 500, 200  # Ajusta para incluir toda la placa

# Variables para manejar el procesamiento
ocr_queue = queue.Queue()
number_samples = []  # Almacena los últimos números detectados
letter_samples = []  # Almacena las últimas letras detectadas
sample_limit = 3  # Número mínimo de muestras antes de tomar una decisión

# Confirmación de letras y números
confirmed_plate = ""  # Placa confirmada (formato completo)
pending_plate = ""  # Placa en proceso de confirmación
pending_count = 0  # Contador para confirmar una nueva placa
confirmation_threshold = 2  # Número de detecciones consecutivas necesarias para confirmar

# Variables globales para los feeds
frame_original = None
frame_processed = None


def start_ffmpeg_process():
    """Inicia el proceso de ffmpeg para la transmisión RTSP."""
    try:
        return (
            ffmpeg
            .input(rtsp_url)
            .output('pipe:', format='rawvideo', pix_fmt='bgr24')
            .run_async(pipe_stdout=True, cmd=ffmpeg_path)
        )
    except FileNotFoundError as e:
        print(f"Error: No se encontró FFmpeg en la ruta especificada. Verifica la instalación y el PATH: {e}")
        raise
    except Exception as e:
        print(f"Error al iniciar FFmpeg: {e}")
        raise


def send_plate_to_server(plate):
    """Enviar la placa detectada al servidor."""
    try:
        requests.post('http://localhost:3000/update', json={'placa': plate})
        print(f"Placa enviada al servidor: {plate}")
    except requests.exceptions.RequestException as e:
        print(f"Error al enviar la placa al servidor: {e}")


def process_ocr():
    """Hilo separado para procesar OCR."""
    global number_samples, letter_samples, confirmed_plate, pending_plate, pending_count

    while True:
        # Esperar un ROI en la cola
        roi_image = ocr_queue.get()
        if roi_image is None:
            break

        try:
            # Preprocesar la imagen para OCR
            gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)

            # Aplicar umbral binario directamente para mejorar velocidad
            _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)

            # Usar Tesseract para extraer texto
            detected_text = pytesseract.image_to_string(binary, config='--psm 8').strip()

            # Filtrar texto para números y letras
            filtered_text = ''.join(char for char in detected_text if char.isalnum())
            letters = ''.join(char for char in filtered_text if char.isalpha() and char.isupper())
            numbers = ''.join(char for char in filtered_text if char.isdigit())

            # Procesar letras y números
            if len(numbers) == 3:
                number_samples.append(numbers)
                if len(number_samples) > sample_limit:
                    number_samples.pop(0)

            if len(letters) == 3:
                letter_samples.append(letters)
                if len(letter_samples) > sample_limit:
                    letter_samples.pop(0)

            # Confirmar formato completo si hay suficientes muestras
            if len(number_samples) >= sample_limit and len(letter_samples) >= sample_limit:
                most_common_numbers = Counter(number_samples).most_common(1)
                most_common_letters = Counter(letter_samples).most_common(1)

                if most_common_numbers and most_common_letters:
                    new_plate = f"{most_common_letters[0][0]} {most_common_numbers[0][0]}"

                    # Confirmar placa solo si el formato es nuevo
                    if new_plate != confirmed_plate:
                        if new_plate == pending_plate:
                            pending_count += 1
                            if pending_count >= confirmation_threshold:
                                confirmed_plate = new_plate
                                print(f"Placa detectada: {confirmed_plate}")

                                # Enviar la placa al servidor en un hilo separado
                                threading.Thread(target=send_plate_to_server, args=(confirmed_plate,)).start()

                                pending_count = 0
                        else:
                            pending_plate = new_plate
                            pending_count = 1

        except Exception as e:
            print(f"Error en OCR: {e}")


def process_frames():
    """Captura y procesa frames continuamente."""
    global frame_original, frame_processed

    process = start_ffmpeg_process()
    while True:
        try:
            # Leer el cuadro de video
            in_bytes = process.stdout.read(width * height * 3)
            if not in_bytes:
                raise ValueError("No se pudo obtener el frame.")
            
            # Convertir a imagen numpy
            frame = np.frombuffer(in_bytes, np.uint8).reshape([height, width, 3])
            frame_original = frame.copy()  # Guardar el frame original

            # Crear una copia de 'frame' para dibujar el ROI y no alterar el original
            frame_processed = frame.copy()

            # Dibujar el ROI
            cv2.rectangle(frame_processed, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (0, 255, 0), 2)

            # Detectar amarillo en la imagen
            hsv = cv2.cvtColor(frame_processed, cv2.COLOR_BGR2HSV)
            lower_yellow = np.array([20, 100, 100])  # Rango para detectar amarillo
            upper_yellow = np.array([30, 255, 255])
            mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
            roi = mask_yellow[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

            # Verificar si hay amarillo en el ROI
            if cv2.countNonZero(roi) > 500:  # Ajusta el umbral de detección
                # Enviar el ROI al hilo de OCR si no está lleno
                if ocr_queue.qsize() < 5:
                    roi_image = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
                    ocr_queue.put(roi_image)

        except Exception as e:
            print(f"Error: {e}. Reintentando en 5 segundos...")
            process.terminate()
            time.sleep(5)
            process = start_ffmpeg_process()


# Rutas de Flask para servir los feeds
@app.route('/video_feed')
def video_feed():
    def generate_frames():
        global frame_original
        while True:
            if frame_original is not None:
                _, buffer = cv2.imencode('.jpg', frame_original)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/processed_feed')
def processed_feed():
    def generate_frames():
        global frame_processed
        while True:
            if frame_processed is not None:
                _, buffer = cv2.imencode('.jpg', frame_processed)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    # Inicia el hilo de OCR
    threading.Thread(target=process_ocr, daemon=True).start()

    # Inicia el hilo de procesamiento de frames
    threading.Thread(target=process_frames, daemon=True).start()

    # Inicia el servidor Flask
    app.run(host='0.0.0.0', port=5000, debug=False)
