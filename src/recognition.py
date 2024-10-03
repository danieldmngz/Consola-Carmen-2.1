import requests
from datetime import datetime
from config import IP_INTERFACE, CAPTURE_PLATE_URL, SNAPSHOT_DIR
from http import client


def upload_image_from_ip():
    try:
        # Consultar el estado del pin
        response = requests.get(IP_INTERFACE)
        if response.status_code != 200:
            print(f"Error al consultar el ESP32: {response.status_code}")
            return

        # Obtener el estado del pin de la respuesta
        result = response.json()
        estado_pin = result.get('estadoPin', None)
        if estado_pin is None:
            print("Error: No se pudo deserializar la respuesta JSON.")
            return

        if estado_pin == 1:
            # Capturar imagen desde la cámara IP
            img_response = requests.get(CAPTURE_PLATE_URL)
            if img_response.status_code != 200:
                print(
                    f"Error al descargar la imagen: {img_response.status_code}"
                )
                return

            # Enviar la imagen descargada al VehicleAPIClient/Carmen para obtener la matrícula
            response = client.send(img_response.content)

            # Simulación del envío de la imagen a un API (VehicleAPIClient)
            plate_text = None  # Resultado simulado de la matrícula
            if hasattr(response.data, 'vehicles') and response.data.vehicles:
                vehicle = response.data.vehicles[0]  # Obtener el primer vehículo de la lista
                if hasattr(vehicle, 'plate') and vehicle.plate.found:
                    plate_text = vehicle.plate.separatedText  # Extraer el texto de la matrícula
                else:
                    plate_text = "SIN_MATRICULA"  # Si no se encuentra matrícula, usar un valor por defecto
 
            # Guardar imagen localmente
            current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"{plate_text}_{current_time}.jpg"
            local_image_path = f"{SNAPSHOT_DIR}/{file_name}"

            with open(local_image_path, 'wb') as file:
                file.write(img_response.content)

            print(f"Imagen guardada en: {local_image_path}")
        else:
            print("El pin está en 0. No se ejecuta tarea.")

    except requests.RequestException as e:
        print(f"Error de red al consultar la imagen: {str(e)}")
    except Exception as e:
        print(f"Error inesperado: {str(e)}")
