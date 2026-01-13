# API SIA Seguros - Clientes

API REST desarrollada con FastAPI para consultar información de clientes desde SQL Server.

## Requisitos

- Python 3.8 o superior
- ODBC Driver 17 for SQL Server (o superior)

### Instalación del ODBC Driver

**Windows:**
- Descargar e instalar desde: https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

**Linux:**
```bash
# Ubuntu/Debian
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql17
```

## Instalación

1. Instalar las dependencias:
```bash
pip install -r requirements.txt
```

## Configuración

1. Copiar el archivo de ejemplo de variables de entorno:
```bash
cp .env.example .env
```

2. Editar el archivo `.env` con tus credenciales:
```env
# Configuración de la base de datos SQL Server
TARGET_SERVER=40.90.233.174,1433
TARGET_DATABASE=SIAsegCaceres
TARGET_USER=sa
TARGET_PASSWORD=Admin2021*

# Configuración de autenticación API
ADMIN_USERNAME=Admin
ADMIN_PASSWORD=Caramelo#2030

# Configuración de paginación
DEFAULT_PAGE_SIZE=10
MAX_PAGE_SIZE=100
```

**Nota:** El archivo `.env` está en `.gitignore` y no se subirá al repositorio por seguridad.

## Ejecución

```bash
python main.py
```

O usando uvicorn directamente:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 5050
```

## Documentación

Una vez ejecutado el servidor, accede a:
- **Swagger UI**: http://localhost:5050/docs
- **ReDoc**: http://localhost:5050/redoc

## Autenticación

La API utiliza autenticación HTTP Basic:
- **Usuario**: Admin
- **Contraseña**: Caramelo#2030

En Swagger, haz clic en el botón "Authorize" e ingresa las credenciales.

## Endpoints

### GET /api/clientes

Obtiene todos los registros de la tabla imclient con paginación y filtros opcionales.

**Parámetros de consulta:**
- `page` (int): Número de página (default: 1)
- `page_size` (int): Tamaño de página (default: 10, máximo: 100)
- `cnomcliente` (string, opcional): Filtro parcial por nombre de cliente
- `crnc` (string, opcional): Filtro parcial por RNC
- `ccedula` (string, opcional): Filtro parcial por cédula
- `cpasaporte` (string, opcional): Filtro parcial por pasaporte

**Ejemplo de respuesta:**
```json
{
  "total": 150,
  "page": 1,
  "page_size": 10,
  "total_pages": 15,
  "data": [
    {
      "id_client": "001",
      "cod_client": 1,
      "nombre": "Juan",
      "apellido": "Pérez",
      ...
    }
  ]
}
```

## Ejemplos de uso

### Obtener primera página de clientes
```
GET /api/clientes?page=1&page_size=10
```

### Buscar por nombre parcial
```
GET /api/clientes?cnomcliente=Juan
```

### Buscar por RNC
```
GET /api/clientes?crnc=123456
```

### Combinar filtros
```
GET /api/clientes?cnomcliente=Juan&ccedula=001
```

