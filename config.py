import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración de la base de datos
TARGET_SERVER = os.getenv("TARGET_SERVER")
TARGET_DATABASE = os.getenv("TARGET_DATABASE")
TARGET_USER = os.getenv("TARGET_USER")
TARGET_PASSWORD = os.getenv("TARGET_PASSWORD")

# Configuración de autenticación
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Configuración de paginación
DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", "10"))
MAX_PAGE_SIZE = int(os.getenv("MAX_PAGE_SIZE", "100"))

