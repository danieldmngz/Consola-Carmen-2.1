import pyodbc

# Cadena de conexión a SQL Server
connection_string = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=172.16.91.126;"            # Dirección del servidor
    "DATABASE=Parqueoo;"               # Nombre de la base de datos
    "UID=usrParqueoo;"                 # Usuario
    "PWD=Us3rP4rqu300*;"               # Contraseña
    "MultipleActiveResultSets=True;"   # Permitir múltiples conjuntos de resultados
    "TrustServerCertificate=Yes;"      # Confiar en el certificado del servidor
)

def get_db_connection():
    """
    Función para conectar a la base de datos y devolver la conexión.
    """
    try:
        conn = pyodbc.connect(connection_string)
        print("Conexión exitosa a la base de datos Parqueoo QA INCOMELEC")
        return conn
    except Exception as e:
        print(f"Error al conectar: {e}")
        return None
