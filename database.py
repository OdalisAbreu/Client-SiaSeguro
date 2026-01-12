import pyodbc
from config import TARGET_SERVER, TARGET_DATABASE, TARGET_USER, TARGET_PASSWORD


def get_db_connection():
    """
    Crea y retorna una conexión a la base de datos SQL Server
    """
    connection_string = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={TARGET_SERVER};"
        f"DATABASE={TARGET_DATABASE};"
        f"UID={TARGET_USER};"
        f"PWD={TARGET_PASSWORD}"
    )
    
    try:
        conn = pyodbc.connect(connection_string)
        return conn
    except Exception as e:
        raise Exception(f"Error al conectar con la base de datos: {str(e)}")


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

