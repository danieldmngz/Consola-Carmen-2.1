import os
import time
import requests
import json
import configparser
import logging
import csv
from datetime import datetime
from carmen_cloud_client import VehicleAPIClient, VehicleAPIOptions, SelectedServices, Locations

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Cargar el archivo de configuración desde la misma carpeta que el script
config_file_path = os.path.join(os.path.dirname(__file__), 'settings.config')

# Leer el archivo de configuración
config = configparser.ConfigParser()
config.read(config_file_path)

# Leer las variables del archivo settings.config
try:
    IP_INTERFACE = config['NETWORK']['IP_INTERFACE'].strip()
    CAPTURE_PLATE_URL = config['NETWORK']['CAPTURE_PLATE_URL'].strip()
    SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')
    IdParqueaderoHorus = config['PARKING']['IdParqueaderoHorus'].strip()
except KeyError as e:
    raise Exception(f"Falta el valor en el archivo de configuración: {e}")

# Verificar si el directorio de snapshots existe
if not os.path.exists(SNAPSHOT_DIR):
    os.makedirs(SNAPSHOT_DIR)
    logging.info(f"Directorio creado: {SNAPSHOT_DIR}")

# Inicializar el cliente de la API
options = VehicleAPIOptions(
    api_key="44f68f1932acd0a4525d6be6e50cc3d5675d97d6",
    services=SelectedServices(anpr=True, mmr=True),
    input_image_location=Locations.Europe.Hungary,
    cloud_service_region="EU"
)
client = VehicleAPIClient(options)

# Conjunto para almacenar matrículas ya registradas
registered_plates = set()

def log_to_csv(data):
    """Log de datos en un archivo CSV."""
    csv_file_path = os.path.join(SNAPSHOT_DIR, 'logs.csv')
    
    # Comprobar si el archivo existe para determinar si se debe escribir el encabezado
    file_exists = os.path.isfile(csv_file_path)

    with open(csv_file_path, mode='a', newline='') as csv_file:
        fieldnames = ['Matricula', 'RutaGuardada', 'FechaEntrada', 'MAC', 'Parqueadero', 'Category', 'Heading', 'Make', 'Model', 'UnicodeText']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()  # Escribir el encabezado solo si el archivo es nuevo
        
        writer.writerow(data)

    logging.info(f"Datos logueados en CSV: {data}")

def upload_image_from_ip():
    """Captura una imagen desde la cámara IP y procesa la matrícula."""
    try:
        logging.info(f"Conectando a la IP: {IP_INTERFACE.strip()}")
        response = requests.get(IP_INTERFACE.strip(), timeout=10)  # Timeout de conexión
        response.raise_for_status()  # Lanza un error si la respuesta no es 200

        result = response.json()  # Parsear la respuesta JSON
        estadoPin1 = result.get('estadoPin1', None)  # Obtener estadoPin1

        if estadoPin1 is None:
            logging.error("Error: No se pudo deserializar la respuesta JSON.")
            return

        if estadoPin1 == 1:  # Solo proceder si estadoPin1 es 1
            logging.info(f"estadoPin1: {estadoPin1}")

            # Capturar imagen desde la cámara IP
            img_response = requests.get(CAPTURE_PLATE_URL.strip(), timeout=10)
            img_response.raise_for_status()

            # Enviar la imagen descargada al VehicleAPIClient
            plate_text = "SIN_MATRICULA"
            category = heading = make = model = unicode_text = None

            try:
                api_response = client.send(img_response.content)
                if hasattr(api_response.data, 'vehicles') and api_response.data.vehicles:
                    vehicle = api_response.data.vehicles[0]
                    if hasattr(vehicle, 'plate') and vehicle.plate.found:
                        plate_text = vehicle.plate.separatedText
                        category = vehicle.category if hasattr(vehicle, 'category') else None
                        heading = vehicle.heading if hasattr(vehicle, 'heading') else None
                        make = vehicle.make if hasattr(vehicle, 'make') else None
                        model = vehicle.model if hasattr(vehicle, 'model') else None
                        unicode_text = vehicle.unicodeText if hasattr(vehicle, 'unicodeText') else None

            except Exception as e:
                logging.error(f"Error al enviar la imagen al API: {e}")
                return

            # Guardar imagen localmente
            current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"{plate_text}_{current_time}.jpg"
            local_image_path = os.path.join(SNAPSHOT_DIR, file_name)

            with open(local_image_path, 'wb') as file:
                file.write(img_response.content)

            # Crear el JSON de respuesta
            formatted_date_time = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            mac_address = "6c:f1:7e:1f:8e:b7"  # Cambia esto por la dirección MAC real
            ubicaciones = {
                "6c:f1:7e:1f:8e:b7": IdParqueaderoHorus
            }
            ubicacion = ubicaciones.get(mac_address, "Ubicacion no encontrada")

            response_data = {
                "Matricula": plate_text,
                "RutaGuardada": local_image_path,
                "FechaEntrada": formatted_date_time,
                "MAC": mac_address,
                "Parqueadero": ubicacion,
                "Category": category,
                "Heading": heading,
                "Make": make,
                "Model": model,
                "UnicodeText": unicode_text
            }

            # Verificar si la matrícula ya ha sido registrada
            if plate_text not in registered_plates:
                # Loguear datos en CSV
                log_to_csv(response_data)
                registered_plates.add(plate_text)  # Agregar matrícula al conjunto

                logging.info(json.dumps(response_data))  # Imprimir el JSON de respuesta
            else:
                logging.info(f"Matrícula ya registrada: {plate_text}")

    except requests.RequestException as e:
        logging.error(f"Error de red al consultar la imagen: {e}")
    except Exception as e:
        logging.error(f"Error inesperado: {e}")

def run_forever():
    """Ejecuta la captura de imágenes de forma indefinida."""
    try:
        while True:
            upload_image_from_ip()
            time.sleep(0.5)  # Pausa de 0.5 segundos antes de la siguiente consulta
    except KeyboardInterrupt:
        logging.info("Proceso detenido manualmente.")

if __name__ == "__main__":
    logging.info("Iniciando proceso de captura de imágenes. Presiona Ctrl+C para detener.")
    run_forever()
