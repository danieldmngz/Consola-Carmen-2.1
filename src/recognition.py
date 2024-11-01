import os
import requests
import json
import configparser
import logging
import aiohttp  # Importar aiohttp para solicitudes asincrónicas
from datetime import datetime
from carmen_cloud_client import VehicleAPIClient, VehicleAPIOptions, SelectedServices, Locations
import uuid
import asyncio  # Importar asyncio para ejecutar funciones asincrónicas

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

# Leer el archivo de configuración
try:
    IP_INTERFACE = config.get('NETWORK', 'IP_INTERFACE').strip()
    CAPTURE_PLATE_URL = config.get('NETWORK', 'CAPTURE_PLATE_URL').strip()
    SNAPSHOT_DIR = config.get('DIRECTORIES', 'SNAPSHOT_DIR').strip()
    IdParqueaderoHorus = config.get('PARKING', 'IdParqueaderoHorus').strip()
    EMAIL = config.get('AUTH', 'EMAIL').strip()
    PASSWORD = config.get('AUTH', 'PASSWORD').strip()
    TokenUrl = "https://api.parqueoo.com/api/authorization/Authenticate"
    InsertBD = "https://servicesqa.parqueoo.com/api/Carmen/InsertarPlaca"
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

# 1. Función para capturar imagen desde la cámara IP y enviar imagen a Carmen y guardar local
async def upload_image_from_ip():
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
            
            # Procesamiento de la imagen con VehicleAPIClient
            try:
                api_response = client.send(img_response.content)
                if hasattr(api_response.data, 'vehicles') and api_response.data.vehicles:
                    vehicle = api_response.data.vehicles[0]
                    if vehicle.plate and vehicle.plate.found:
                        plate_text = vehicle.plate.separatedText
                        category = vehicle.plate.category
                        heading = vehicle.mmr.heading
                        make = vehicle.mmr.make
                        model = vehicle.mmr.model
                        unicode_text = vehicle.plate.unicodeText

                # Añadir la información detallada en el log
                logging.info(f"Imagen procesada con éxito: Placa: {plate_text}, Categoría: {category}, Heading: {heading}, Make: {make}, Model: {model}, Unicode Text: {unicode_text}")

            except Exception as e:
                logging.error(f"Error al enviar la imagen al API: {e}")
                return

            # Verificar si el texto de la placa es "CERRADA" o "SIN_MATRICULA" para omitir el guardado
            if plate_text in ["CERRADA", "SIN_MATRICULA"]:
                logging.info(f"Placa '{plate_text}' detectada. No se guardará el registro.")
                return  # Omitir guardado si plate_text es "CERRADA" o "SIN_MATRICULA"

            # Guardar imagen localmente
            current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"{plate_text}_{current_time}.jpg"
            local_image_path = os.path.join(SNAPSHOT_DIR, file_name)

            with open(local_image_path, 'wb') as file:
                file.write(img_response.content)

            # Obtener la fecha actual
            fecha_snapshot = datetime.now().isoformat()
            mac_address = "6c:f1:7e:1f:8e:b7"
            ubicaciones = {"6c:f1:7e:1f:8e:b7": IdParqueaderoHorus}
            ubicacion_id = ubicaciones.get(mac_address)

            # Insertar en la base de datos
            await insertar_en_base_de_datos(plate_text, local_image_path, fecha_snapshot, mac_address, ubicacion_id, EMAIL, EMAIL, category, heading, make, model, unicode_text)

        else:
            logging.info("Estado de pin 1 no activo. No se capturó ninguna imagen.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error al conectar a la cámara IP o capturar la imagen: {str(e)}")

# 2. Definición de función asíncrona para insertar datos con endpoint en la base de datos de parqueoo QA
async def insertar_en_base_de_datos(placa, ruta_snapshot, fecha_snapshot, direccion_mac, parqueadero_id, created_by, updated_by, category, heading, make, model, unicode_text):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Obtener el token de autenticación
            token = await obtener_token_autenticacion(EMAIL, PASSWORD)
            #logging.info("Generado token: ", {token})
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
            response = requests.post(InsertBD, json=data, headers=headers)

            # Log detallado del estado HTTP
            logging.info(f"POST a {InsertBD} | Estado HTTP: {response.status_code}")

            if response.status_code == 200:
                logging.info(f"Datos insertados correctamente: {data}")
                return True
            else:
                logging.warning(f"Error al insertar. Estado: {response.status_code}, Respuesta: {response.text}")
                await asyncio.sleep(2)  # Esperar antes de reintentar

        except Exception as e:
            logging.error(f"Error al insertar en el endpoint: {str(e)}")
            await asyncio.sleep(2)  # Esperar antes de reintentar

    logging.error("No se pudo insertar los datos después de múltiples intentos.")

# 3. Definición de función asíncrona para obtener token de autenticación de parqueoo
async def obtener_token_autenticacion(EMAIL, PASSWORD):
    """Obtiene un token de autenticación usando las credenciales proporcionadas."""
    try:
        token_request = {
            "username": EMAIL,
            "password": PASSWORD
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(TokenUrl, json=token_request) as response:
                if response.status == 200:
                    json_response = await response.json()
                    logging.info("Token de autenticación obtenido correctamente.")
                    return json_response['token']
                else:
                    logging.error(f"Error al obtener token: {response.status}, Respuesta: {await response.text()}")
                    return None
    except Exception as e:
        logging.error(f"Error al obtener token de autenticación: {str(e)}")
        return None

# 4. Función principal asíncrona para controlar la ejecución
async def main():
    while True:
        await upload_image_from_ip()  # Llamar a la función para capturar la imagen
        await asyncio.sleep(5)  # Esperar un tiempo antes de volver a intentar

# 5. Ejecución del script
if __name__ == '__main__':
    asyncio.run(main())
