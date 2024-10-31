import os
import time
import requests
import json
import configparser
import logging
import aiohttp  # Importar aiohttp para solicitudes asincrónicas
from datetime import datetime
from carmen_cloud_client import VehicleAPIClient, VehicleAPIOptions, SelectedServices, Locations
import uuid

# Cargar archivo de configuración
config = configparser.ConfigParser()
config.read('settings.config')

# Obtener ruta de logs desde el archivo de configuración
log_dir = config.get('DIRECTORIES', 'LOG_DIR', fallback=os.path.expanduser("~"))  # Ruta alternativa si LOG_DIR no está definida
log_file_path = os.path.join(log_dir, 'application.log')

# Crear el directorio de logs si no existe
os.makedirs(log_dir, exist_ok=True)

# Configurar el logger para registrar eventos
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file_path), logging.StreamHandler()]
)

# Cargar el archivo de configuración desde la misma carpeta que el script
config_file_path = os.path.join(os.path.dirname(__file__), 'settings.config')

# Leer el archivo de configuración
config = configparser.ConfigParser()
config.read(config_file_path)

# Leer las variables del archivo settings.config
try:
    IP_INTERFACE = config.get('NETWORK', 'IP_INTERFACE').strip()
    CAPTURE_PLATE_URL = config.get('NETWORK', 'CAPTURE_PLATE_URL').strip()
    SNAPSHOT_DIR = config.get('DIRECTORIES', 'SNAPSHOT_DIR').strip()
    IdParqueaderoHorus = config.get('PARKING', 'IdParqueaderoHorus').strip()
    EMAIL = config.get('AUTH', 'EMAIL').strip()
    PASSWORD = config.get('AUTH', 'PASSWORD').strip()
    # Definición de TokenUrl para autenticación
    TokenUrl = "https://api.parqueoo.com/api/authorization/Authenticate"
except KeyError as e:
    logging.critical(f"Falta el valor en el archivo de configuración: {e}")
    raise

# Verificar si el directorio de snapshots existe
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
logging.info(f"Directorio de snapshots verificado: {SNAPSHOT_DIR}")

# Inicializar el cliente de la API de detección de vehículos
options = VehicleAPIOptions(
    api_key="fcd1fafd54abed9fc0b1c30b235e5a3931c8b0bb",
    services=SelectedServices(anpr=True, mmr=True),
    input_image_location=Locations.Europe.Hungary,
    cloud_service_region="EU"
)
client = VehicleAPIClient(options)

# Definición de función asíncrona para insertar datos en la base de datos
async def insertar_en_base_de_datos(placa, ruta_snapshot, fecha_snapshot, direccion_mac, parqueadero_id, created_by, updated_by, category, heading, make, model, unicode_text):
    try:
        # Obtener el token de autenticación
        token = await obtener_token_autenticacion(EMAIL, PASSWORD)

        # Validar que el token fue obtenido
        if not token:
            logging.error("No se pudo obtener un token, abortando la inserción.")
            return

        # Datos a enviar en la solicitud POST
        data = {
            "Id": str(uuid.uuid4()),
            "CreateTime": fecha_snapshot,
            "UpdateTime": fecha_snapshot,
            "CreatedBy": created_by,
            "UpdatedBy": updated_by,
            "IdParqueaderoHorus": parqueadero_id,
            "Placa": placa,
            "DireccionMAC": direccion_mac,
            "FechaSnapshot": fecha_snapshot,
            "RutaSnapshot": ruta_snapshot,
            "Category": category,
            "Heading": heading,
            "Make": make,
            "Model": model,
            "UnicodeText": unicode_text
        }

        # Realizar la solicitud POST al endpoint usando el token
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.post("https://servicesqa.parqueoo.com/api/Carmen/InsertarPlaca", json=data, headers=headers)
        
        # Log detallado del estado HTTP
        logging.info(f"POST a https://servicesqa.parqueoo.com/api/Carmen/InsertarPlaca | Estado HTTP: {response.status_code}")
        
        if response.status_code == 200:
            logging.info(f"Datos insertados correctamente: {data}")
        else:
            logging.warning(f"Error al insertar. Estado: {response.status_code}, Respuesta: {response.text}")
            
    except Exception as e:
        logging.error(f"Error al insertar en el endpoint: {str(e)}")

# Definición de función asíncrona para obtener token de autenticación
async def obtener_token_autenticacion(EMAIL, PASSWORD):
    """Obtiene un token de autenticación usando las credenciales proporcionadas."""
    try:
        token_request = {
            "username": EMAIL,
            "password": PASSWORD
        }
        json_request = json.dumps(token_request)
        headers = {'Content-Type': 'application/json'}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(TokenUrl, data=json_request, headers=headers) as token_response:
                if token_response.status != 200:
                    logging.error("Fallo en la obtención del token de autenticación.")
                    return None
                
                token_result = await token_response.json()
                return token_result['token']  # Asumiendo que el token está en esta clave
    except Exception as e:
        logging.error(f"Error al obtener el token de autenticación: {e}")
        return None

# Función para capturar imagen desde la cámara IP
def upload_image_from_ip():
    """Captura una imagen desde la cámara IP y procesa la matrícula."""
    try:
        logging.info(f"Conectando a la IP: {IP_INTERFACE}")
        response = requests.get(IP_INTERFACE, timeout=10)  # Aumentar el timeout si es necesario
        response.raise_for_status()
        
        result = response.json()
        estadoPin1 = result.get('estadoPin1')

        if estadoPin1 is None:
            logging.error("Error: No se pudo deserializar la respuesta JSON.")
            return

        # Verificar si el pin está activo
        if estadoPin1 == 1:
            img_response = requests.get(CAPTURE_PLATE_URL, timeout=10)
            img_response.raise_for_status()

            # Inicialización de variables de respuesta
            plate_text = "SIN_MATRICULA"
            category = heading = make = model = unicode_text = None

            # Procesamiento de la imagen con VehicleAPIClient
            try:
                api_response = client.send(img_response.content)
                if hasattr(api_response.data, 'vehicles') and api_response.data.vehicles:
                    vehicle = api_response.data.vehicles[0]
                    if vehicle.plate and vehicle.plate.found:
                        plate_text = vehicle.plate.separatedText
                        category = getattr(vehicle, 'category', None)
                        heading = getattr(vehicle, 'heading', None)
                        make = getattr(vehicle, 'make', None)
                        model = getattr(vehicle, 'model', None)
                        unicode_text = getattr(vehicle, 'unicodeText', None)
                logging.info("Imagen procesada con éxito en VehicleAPIClient")

            except Exception as e:
                logging.error(f"Error al enviar la imagen al API: {e}")
                return

            # Guardar imagen localmente
            current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"{plate_text}_{current_time}.jpg"
            local_image_path = os.path.join(SNAPSHOT_DIR, file_name)

            with open(local_image_path, 'wb') as file:
                file.write(img_response.content)

            formatted_date_time = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            mac_address = "6c:f1:7e:1f:8e:b7"
            ubicaciones = {"6c:f1:7e:1f:8e:b7": IdParqueaderoHorus}
            ubicacion_id = ubicaciones.get(mac_address)
        else:
            logging.info("Estado de pin 1 no activo. No se capturó ninguna imagen.")
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Error al conectar a la cámara IP o capturar la imagen: {str(e)}")

if __name__ == "__main__":
    try:
        while True:
            # Primero, verifica el estado de la cámara IP
            logging.info("Verificando el estado de la cámara IP...")
            response = requests.get(IP_INTERFACE, timeout=10)  # Aumentar el timeout si es necesario
            response.raise_for_status()

            result = response.json()
            estadoPin1 = result.get('estadoPin1')
            estadoPin0 = result.get('estadoPin0')  # Suponiendo que este es el nombre del estado

            if estadoPin1 is None or estadoPin0 is None:
                logging.error("Error: No se pudo deserializar la respuesta JSON.")
                time.sleep(3)
                continue  # Continuar a la siguiente iteración si hay un error

            logging.info(f"Estado Pin 1: {estadoPin1}, Estado Pin 0: {estadoPin0}")

            # Si estadoPin1 está activo, captura la imagen
            if estadoPin1 == 1:
                  upload_image_from_ip()  # Asegúrate de usar await aquí si es una función async
            else:
                logging.info("Estado de pin 1 no activo. No se capturó ninguna imagen.")

            # Ajusta el intervalo de tiempo entre chequeos según tu necesidad
            time.sleep(3)  # Esperar unos segundos antes del siguiente ciclo

    except Exception as e:
        logging.error(f"Error general en el script: {str(e)}")
