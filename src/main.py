from recognition import upload_image_from_ip
from db_connection import get_db_connection

def main():
    # Conectar a la base de datos
    conn = get_db_connection()
    
    if conn:
        # Ejecuta la lógica principal de reconocimiento si la conexión fue exitosa
        upload_image_from_ip()
    
if __name__ == "__main__":
    main()
