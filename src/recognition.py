from datetime import datetime
from config import IP_INTERFACE, CAPTURE_PLATE_URL, SNAPSHOT_DIR
import time  # Para usar time.sleep y pausar el ciclo
import requests
import json
from carmen_cloud_client import VehicleAPIClient, VehicleAPIOptions, SelectedServices, Locations

# Inicializar el cliente de la API con las opciones
options = VehicleAPIOptions(
    api_key="44f68f1932acd0a4525d6be6e50cc3d5675d97d6",
    services=SelectedServices(anpr=True, mmr=True),
    input_image_location=Locations.Europe.Hungary,
    cloud_service_region="EU"
)
client = VehicleAPIClient(options)

def upload_image_from_ip():
    # Contador inicial
    contador_mensaje = 0
    try:
        # Consultar el estado del pin
        response = requests.get(IP_INTERFACE)
        if response.status_code != 200:
            print(json.dumps({"error": f"Error al consultar el ESP32: {response.status_code}"}))
            return

        # Obtener el estado del pin de la respuesta
        result = response.json()
        estado_pin = result.get('estadoPin', None)
        if estado_pin is None:
            print(json.dumps({"error": "Error: No se pudo deserializar la respuesta JSON."}))
            return

        if estado_pin == 1:
            # Capturar imagen desde la cámara IP
            img_response = requests.get(CAPTURE_PLATE_URL)
            if img_response.status_code != 200:
                print(json.dumps({"error": f"Error al descargar la imagen: {img_response.status_code}"}))
                return

            # Enviar la imagen descargada al VehicleAPIClient para obtener la matrícula
            try:
                api_response = client.send(img_response.content)  # Usar el cliente de la API

                # Extraer el campo separatedText de la respuesta
                plate_text = None
                if hasattr(api_response.data, 'vehicles') and api_response.data.vehicles:
                    vehicle = api_response.data.vehicles[0]  # Obtener el primer vehículo de la lista
                    if hasattr(vehicle, 'plate') and vehicle.plate.found:
                        plate_text = vehicle.plate.separatedText  # Extraer el texto de la matrícula
                    else:
                        plate_text = "SIN_MATRICULA"  # Si no se encuentra matrícula, usar un valor por defecto
                else:
                    plate_text = "SIN_MATRICULA"  # Si no se encuentra información de vehículos

            except Exception as e:
                print(json.dumps({"error": f"Error al enviar la imagen al API: {str(e)}"}))
                return

            # Guardar imagen localmente
            current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"{plate_text}_{current_time}.jpg"
            local_image_path = f"{SNAPSHOT_DIR}/{file_name}"

            with open(local_image_path, 'wb') as file:
                file.write(img_response.content)

            # Crear el JSON de respuesta
            formatted_date_time = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            mac_address = "6c:f1:7e:1f:8e:b7"  # Cambia esto por la dirección MAC real
            ubicaciones = {
                "6c:f1:7e:1f:8e:b7": "98"
                # Puedes agregar más asociaciones de MAC y ubicaciones aquí
            }
            ubicacion = ubicaciones.get(mac_address, "Ubicacion no encontrada")

            response_data = {
                "Matricula": plate_text,
                "RutaGuardada": local_image_path,
                "Fecha_entrada": formatted_date_time,
                "Parqueadero": {
                    "MAC": mac_address,
                    "Parqueadero": ubicacion
                },
            }

            print(json.dumps(response_data))  # Imprimir el JSON de respuesta

        else:
            # Contador que se incrementa indefinidamente mientras el estado del pin sea 0
                print(({"message": fr"El pin del LOOP esta en 0. No se ejecuta tarea."}))
                '''
                 while True:
                    contador_mensaje += 1  # Incrementar el contador
                    print(({"message": {fr"LOOP # Detectado" + contador_mensaje}}))
                    time.sleep(1)  # Pausar 0.2 segundos
                '''
               
    except requests.RequestException as e:
        print(json.dumps({"error": f"Error de red al consultar la imagen: {str(e)}"}))
    except Exception as e:
        print(json.dumps({"error": f"Error inesperado: {str(e)}"}))


def run_forever():
    try:
        while True:
            upload_image_from_ip()
            time.sleep(0.1)  # Pausa de 0.2 segundos antes de la siguiente consulta
    except KeyboardInterrupt:
        print("Proceso detenido manualmente.")


if __name__ == "_main_":
    print("Iniciando proceso de captura de imágenes. Presiona Ctrl+C para detener.")
run_forever()