import os
import time
import requests
import json
import configparser
import pyodbc
import logging
from datetime import datetime
from carmen_cloud_client import VehicleAPIClient, VehicleAPIOptions, SelectedServices, Locations
import uuid  # Importa el módulo uuid para generar GUIDs

# Configuración de logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# Cargar el archivo de configuración desde la misma carpeta que el script
config_file_path = os.path.join(os.path.dirname(__file__), 'settings.config')

# Leer el archivo de configuración
config = configparser.ConfigParser()
config.read(config_file_path)

# Leer las variables del archivo settings.config
try:
    IP_INTERFACE = config['NETWORK']['IP_INTERFACE'].strip()
    CAPTURE_PLATE_URL = config['NETWORK']['CAPTURE_PLATE_URL'].strip()
    SNAPSHOT_DIR = config['DIRECTORIES']['SNAPSHOT_DIR'].strip()
    IdParqueaderoHorus = config['PARKING']['IdParqueaderoHorus'].strip()
except KeyError as e:
    raise Exception(f"Falta el valor en el archivo de configuración: {e}")

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

def insertar_en_base_de_datos(placa, ruta_snapshot, fecha_snapshot, direccion_mac, parqueadero_id, created_by, updated_by, category, heading, make, model, unicode_text):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        ahora = datetime.now()
        nuevo_id = uuid.uuid4()

        query = """
        INSERT INTO PlacasAuditoria (Id, CreateTime, UpdateTime, CreatedBy, UpdatedBy, IdParqueaderoHorus, Placa, DireccionMAC, FechaSnapshot, RutaSnapshot, Category, Heading, Make, Model, UnicodeText)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        values = (nuevo_id, ahora, ahora, created_by, updated_by, parqueadero_id, placa, direccion_mac, fecha_snapshot, ruta_snapshot, category, heading, make, model, unicode_text)

        cursor.execute(query, values)
        connection.commit()

        logging.info(f"Datos insertados correctamente en la tabla PlacasAuditoria: {placa}, {category}, {heading}, {make}, {model}, {unicode_text}")

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
        logging.info(f"Conectando a la IP: {IP_INTERFACE.strip()}")
        response = requests.get(IP_INTERFACE.strip(), timeout=1000)  # Aumentar el timeout
        response.raise_for_status()  # Lanza un error si la respuesta no es 200

        result = response.json()  # Parsear la respuesta JSON
        estadoPin1 = result.get('estadoPin1', None)  # Obtener estadoPin1

        if estadoPin1 is None:
            logging.error("Error: No se pudo deserializar la respuesta JSON.")
            return

        if estadoPin1 == 1:
            logging.info(f"estadoPin1: {estadoPin1}")  # Solo imprimir si estadoPin1 es 1

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
                "Fecha_entrada": formatted_date_time,
                "Parqueadero": {
                    "MAC": mac_address,
                    "Parqueadero": ubicacion
                },
                "Category": category,
                "Heading": heading,
                "Make": make,
                "Model": model,
                "UnicodeText": unicode_text
            }

            # Insertar los datos en la base de datos
            insertar_en_base_de_datos(
                response_data["Matricula"],        # Placa
                response_data["RutaGuardada"],     # RutaSnapshot
                formatted_date_time,                # FechaSnapshot
                mac_address,                        # DireccionMAC
                IdParqueaderoHorus,                 # IdParqueaderoHorus
                created_by=f"Creator_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",  
                updated_by=f"Updater_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",  
                category=response_data["Category"], # Category
                heading=response_data["Heading"],   # Heading
                make=response_data["Make"],         # Make
                model=response_data["Model"],       # Model
                unicode_text=response_data["UnicodeText"]  # UnicodeText
            )

            logging.info(json.dumps(response_data))  # Imprimir el JSON de respuesta

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
