import os
import time
import requests
import json
import configparser
import pyodbc
import logging
from datetime import datetime
from carmen_cloud_client import VehicleAPIClient, VehicleAPIOptions, SelectedServices, Locations

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Cargar el archivo de configuración
config = configparser.ConfigParser()
config.read('C:\\Users\\SV CALLE 98\\Documents\\Consola-Carmen-2.1\\Consola-Carmen-2.1\\settings.config')

# Leer las variables del archivo settings.config
IP_INTERFACE = config['NETWORK']['IP_INTERFACE']
CAPTURE_PLATE_URL = config['NETWORK']['CAPTURE_PLATE_URL']
SNAPSHOT_DIR = config['DIRECTORIES']['SNAPSHOT_DIR']
IdParqueaderoHorus = config['PARKING']['IdParqueaderoHorus']

# Verificar si el directorio de snapshots existe
if not os.path.exists(SNAPSHOT_DIR):
    os.makedirs(SNAPSHOT_DIR)
    logging.info(f"Directorio creado: {SNAPSHOT_DIR}")

# Cadena de conexión a SQL Server
connection_string = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=172.16.91.126;"
    "DATABASE=Parqueoo;"
    "UID=usrParqueoo;"
    "PWD=Us3rP4rqu300*;"
    "MultipleActiveResultSets=True;"
    "TrustServerCertificate=Yes;"
)

def get_db_connection():
    """Conectar a la base de datos y devolver la conexión."""
    while True:  # Intentar hasta que la conexión sea exitosa
        try:
            conn = pyodbc.connect(connection_string)
            logging.info("Conexión exitosa a la base de datos Parqueoo QA INCOMELEC")
            return conn
        except Exception as e:
            logging.error(f"Error al conectar a la base de datos: {e}. Reintentando en 5 segundos...")
            time.sleep(5)  # Esperar antes de reintentar

# Inicializar el cliente de la API
options = VehicleAPIOptions(
    api_key="44f68f1932acd0a4525d6be6e50cc3d5675d97d6",
    services=SelectedServices(anpr=True, mmr=True),
    input_image_location=Locations.Europe.Hungary,
    cloud_service_region="EU"
)
client = VehicleAPIClient(options)

import uuid  # Importa el módulo uuid para generar GUIDs

def insertar_en_base_de_datos(placa, ruta_snapshot, fecha_snapshot, direccion_mac, parqueadero_id):
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Generamos la fecha y hora actual
        ahora = datetime.now()
        
        # Genera un nuevo GUID para el Id
        nuevo_id = uuid.uuid4()  # Genera un nuevo GUID

        query = """
        INSERT INTO PlacasAuditoria (Id, CreateTime, UpdateTime, IdParqueaderoHorus, Placa, DireccionMAC, FechaSnapshot, RutaSnapshot)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # Proporciona el nuevo GUID en los valores
        values = (nuevo_id, ahora, ahora, parqueadero_id, placa, direccion_mac, fecha_snapshot, ruta_snapshot)

        cursor.execute(query, values)
        connection.commit()

        logging.info(f"Datos insertados correctamente en la tabla PlacasAuditoria: {placa}")

    except Exception as e:
        logging.error(f"Error al insertar en la base de datos: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def upload_image_from_ip():
    """Captura una imagen desde la cámara IP y procesa la matrícula."""
    try:
        # Consultar el estado del pin
        response = requests.get(IP_INTERFACE)
        response.raise_for_status()

        result = response.json()
        estado_pin = result.get('estadoPin', None)

        if estado_pin is None:
            logging.error("Error: No se pudo deserializar la respuesta JSON.")
            return

        if estado_pin == 1:
            # Capturar imagen desde la cámara IP
            img_response = requests.get(CAPTURE_PLATE_URL)
            img_response.raise_for_status()

            # Enviar la imagen descargada al VehicleAPIClient
            plate_text = "SIN_MATRICULA"
            try:
                api_response = client.send(img_response.content)
                if hasattr(api_response.data, 'vehicles') and api_response.data.vehicles:
                    vehicle = api_response.data.vehicles[0]
                    if hasattr(vehicle, 'plate') and vehicle.plate.found:
                        plate_text = vehicle.plate.separatedText

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
                "Fecha_entrada": formatted_date_time,
                "Parqueadero": {
                    "MAC": mac_address,
                    "Parqueadero": ubicacion
                },
            }

            # Insertar los datos en la base de datos utilizando response_data
            insertar_en_base_de_datos(
                response_data["Matricula"],        # Placa
                response_data["RutaGuardada"],     # RutaSnapshot
                formatted_date_time,                # FechaSnapshot
                mac_address,                        # DireccionMAC
                IdParqueaderoHorus                 # IdParqueaderoHorus
            )

            logging.info(json.dumps(response_data))  # Imprimir el JSON de respuesta

        else:
            logging.info("El pin del LOOP está en 0. No se ejecuta tarea.")

    except requests.RequestException as e:
        logging.error(f"Error de red al consultar la imagen: {e}")
    except Exception as e:
        logging.error(f"Error inesperado: {e}")

def run_forever():
    """Ejecuta la captura de imágenes de forma indefinida."""
    try:
        while True:
            upload_image_from_ip()
            time.sleep(0.5)  # Pausa de 0.1 segundos antes de la siguiente consulta
    except KeyboardInterrupt:
        logging.info("Proceso detenido manualmente.")

if __name__ == "__main__":
    logging.info("Iniciando proceso de captura de imágenes. Presiona Ctrl+C para detener.")
    run_forever()
