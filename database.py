import pyodbc
import logging
import traceback
from fastapi import HTTPException
from config import TARGET_SERVER, TARGET_DATABASE, TARGET_USER, TARGET_PASSWORD

logger = logging.getLogger(__name__)


def get_db_connection():
    """
    Crea y retorna una conexión a la base de datos SQL Server
    """
    connection_string = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};Encrypt=yes;TrustServerCertificate=yes;"
        f"SERVER={TARGET_SERVER};"
        f"DATABASE={TARGET_DATABASE};"
        f"UID={TARGET_USER};"
        f"PWD={TARGET_PASSWORD}"
    )
    
    try:
        conn = pyodbc.connect(connection_string)
        # Las columnas char/varchar de la BD guardan texto en Windows-1252
        # (español con acentos). Sin esto, pyodbc intenta decodificar como
        # UTF-8 y falla con bytes como 0xe9 ('é').
        conn.setdecoding(pyodbc.SQL_CHAR, encoding="cp1252")
        conn.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-16-le")
        conn.setencoding(encoding="cp1252")
        return conn
    except Exception as e:
        logger.error(
            f"Error al conectar con la base de datos",
            exc_info=True,
            extra={
                "server": TARGET_SERVER,
                "database": TARGET_DATABASE,
                "user": TARGET_USER,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error al conectar con la base de datos: {str(e)}"
        )


def execute_query(query, params=None):
    """
    Ejecuta una consulta SQL y retorna los resultados
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Obtener nombres de columnas
        columns = [column[0] for column in cursor.description]
        
        # Obtener todos los resultados
        results = cursor.fetchall()
        
        # Convertir a lista de diccionarios
        data = []
        for row in results:
            row_dict = {}
            for i, col in enumerate(columns):
                row_dict[col] = row[i]
            data.append(row_dict)
        
        return data
    finally:
        conn.close()

