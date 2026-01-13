from fastapi import FastAPI, Query, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Optional, List
from math import ceil
import pyodbc
import logging
import traceback
from datetime import datetime
import os
import re
from config import (
    TARGET_SERVER, TARGET_DATABASE, TARGET_USER, TARGET_PASSWORD,
    DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
)
from models import ClientResponse, PaginatedResponse, KYCResponse, PaginatedKYCResponse, TotalesPorEstado
from auth import verify_credentials

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api_errors.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="API SIA Seguros - Clientes",
    description="API para consultar información de clientes desde SQL Server",
    version="1.0.0"
)

# Exception handler global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Manejador global de excepciones para capturar todos los errores no manejados
    """
    logger.error(
        f"Error no manejado en {request.method} {request.url.path}",
        exc_info=True,
        extra={
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc()
        }
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Error interno del servidor",
            "detail": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )


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


@app.get("/")
async def root():
    """
    Endpoint raíz de la API
    """
    return {
        "message": "API SIA Seguros - Clientes",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/api/clientes", response_model=PaginatedResponse)
async def get_clientes(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Tamaño de página"),
    cnomcliente: Optional[str] = Query(None, description="Filtro parcial por nombre de cliente"),
    crnc: Optional[str] = Query(None, description="Filtro parcial por RNC"),
    ccedula: Optional[str] = Query(None, description="Filtro parcial por cédula"),
    cpasaporte: Optional[str] = Query(None, description="Filtro parcial por pasaporte"),
    tipo_cliente: Optional[str] = Query(None, description="Filtro por tipo de cliente"),
    estatus: Optional[str] = Query(None, description="Filtro por estatus"),
    sucursal: Optional[str] = Query(None, description="Filtro por sucursal (código)"),
    es_prospecto: Optional[str] = Query(None, description="Filtro por tipo: C=Cliente, P=Prospecto"),
    username: str = Depends(verify_credentials)
):
    """
    Obtiene todos los registros de clientes con paginación y filtros opcionales.
    
    Filtros disponibles:
    - cnomcliente: Nombre del cliente (búsqueda parcial)
    - crnc: RNC (búsqueda parcial)
    - ccedula: Cédula (búsqueda parcial)
    - cpasaporte: Pasaporte (búsqueda parcial)
    - tipo_cliente: Tipo de cliente (exacto)
    - estatus: Estatus del cliente (exacto)
    - sucursal: Código de sucursal (exacto)
    - es_prospecto: C=Cliente, P=Prospecto (exacto)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Construir la consulta base
        base_query = """
            SELECT 
                RTRIM(c.ccodclien) AS id_client, 
                c.icodclien AS cod_client,
                c.inumclient AS num_client,
                RTRIM(c.cnomcliente) AS nombre,
                RTRIM(c.capellidos) AS apellido,
                RTRIM(c.ccedula) AS cedula,
                RTRIM(c.crnc) AS rnc,
                RTRIM(c.cstatus) AS estatus,
                RTRIM(c.cdirecofi1) AS dirreccion_1,
                RTRIM(c.cdirecofi2) AS dirreccion_2,
                RTRIM(c.cdirecofi3) AS dirreccion_3,
                RTRIM(c.cdireccas1) AS dirreccion_casa_1,
                RTRIM(c.cdireccas2) AS dirreccion_casa_2,
                RTRIM(c.cdireccas3) AS dirreccion_casa_3,
                RTRIM(c.ctipotel1) AS tipo_telefono,
                RTRIM(c.ctipotel2) AS tipo_celular_1,
                RTRIM(c.cemail1) AS email_1,
                RTRIM(c.cemail2) AS email_2,
                RTRIM(tc.tipo) AS tipo_cliente,
                CAST(c.dfechnac AS DATE) AS fecha_nacimiento,
                CAST(c.fechaCreacionCliente AS DATE) AS fecha_creacion, 
                CAST(c.dfechingreso AS DATE) AS fecha_ingreso,
                RTRIM(ac.cdescripcion) AS activa_comercial,
                RTRIM(cd.sexo) AS sexo,
                RTRIM(cd.profesion) AS profecion,
                RTRIM(cd.cargo) AS cargo, 
                RTRIM(cd.empresa) AS empresa,
                ac.ponderacion AS ponderacion,
                RTRIM(s.cdescripcion) AS sucursal,
                RTRIM(c.cprospecto) AS es_procpecto,
                RTRIM(c.cnumtel1) AS telefono_oficina,
                RTRIM(c.cnumtel2) AS numero_celular    
            FROM imclient c
            INNER JOIN imclientdet cd ON cd.ccodclien = c.ccodclien
            LEFT JOIN imcliact ac ON ac.ccodcliact = c.ccodcliact
            LEFT JOIN imtipclient tc ON tc.imtipclientid = cd.imtipclientid
            LEFT JOIN imsucursal s ON s.ccodsucursal = cd.ccodsucursal
            WHERE 1=1
        """
        
        # Construir condiciones de filtro
        filter_conditions = []
        params = []
        
        if cnomcliente:
            filter_conditions.append("c.cnomcliente LIKE ?")
            params.append(f"%{cnomcliente}%")
        
        if crnc:
            filter_conditions.append("c.crnc LIKE ?")
            params.append(f"%{crnc}%")
        
        if ccedula:
            filter_conditions.append("c.ccedula LIKE ?")
            params.append(f"%{ccedula}%")
        
        if cpasaporte:
            filter_conditions.append("c.cpasaporte LIKE ?")
            params.append(f"%{cpasaporte}%")
        
        if tipo_cliente:
            filter_conditions.append("tc.tipo = ?")
            params.append(tipo_cliente)
        
        if estatus:
            filter_conditions.append("c.cstatus = ?")
            params.append(estatus)
        
        if sucursal:
            filter_conditions.append("s.ccodsucursal = ?")
            params.append(sucursal)
        
        if es_prospecto:
            filter_conditions.append("c.cprospecto = ?")
            params.append(es_prospecto.upper())
        
        # Agregar condiciones de filtro a la consulta
        if filter_conditions:
            base_query += " AND " + " AND ".join(filter_conditions)
        
        # Consulta para contar el total de registros
        count_query = f"SELECT COUNT(*) as total FROM ({base_query}) as filtered"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        
        # Calcular paginación
        total_pages = ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size
        
        # Consulta paginada
        paginated_query = f"""
            SELECT * FROM (
                {base_query}
            ) as filtered
            ORDER BY cod_client
            OFFSET ? ROWS
            FETCH NEXT ? ROWS ONLY
        """
        
        params_with_pagination = params + [offset, page_size]
        cursor.execute(paginated_query, params_with_pagination)
        
        # Obtener nombres de columnas
        columns = [column[0] for column in cursor.description]
        
        # Obtener resultados
        results = cursor.fetchall()
        
        # Convertir a lista de diccionarios
        data = []
        for row in results:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                # Eliminar espacios en blanco al final de campos de texto
                if value is not None and isinstance(value, str):
                    value = value.rstrip()
                # Convertir None a None explícitamente
                row_dict[col] = value if value is not None else None
            data.append(ClientResponse(**row_dict))
        
        return PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            data=data
        )
        
    except pyodbc.Error as e:
        logger.error(
            f"Error de base de datos en endpoint /api/clientes",
            exc_info=True,
            extra={
                "endpoint": "/api/clientes",
                "error_type": "pyodbc.Error",
                "error_message": str(e),
                "query_params": {
                    "page": page,
                    "page_size": page_size,
                    "cnomcliente": cnomcliente,
                    "crnc": crnc,
                    "ccedula": ccedula,
                    "cpasaporte": cpasaporte,
                    "tipo_cliente": tipo_cliente,
                    "estatus": estatus,
                    "sucursal": sucursal,
                    "es_prospecto": es_prospecto
                },
                "traceback": traceback.format_exc()
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error en la base de datos: {str(e)}"
        )
    except Exception as e:
        logger.error(
            f"Error inesperado en endpoint /api/clientes",
            exc_info=True,
            extra={
                "endpoint": "/api/clientes",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query_params": {
                    "page": page,
                    "page_size": page_size,
                    "cnomcliente": cnomcliente,
                    "crnc": crnc,
                    "ccedula": ccedula,
                    "cpasaporte": cpasaporte,
                    "tipo_cliente": tipo_cliente,
                    "estatus": estatus,
                    "sucursal": sucursal,
                    "es_prospecto": es_prospecto
                },
                "traceback": traceback.format_exc()
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error inesperado: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@app.get("/api/kyc", response_model=PaginatedKYCResponse)
async def get_kyc(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Tamaño de página"),
    cnomcliente: Optional[str] = Query(None, description="Filtro parcial por nombre de cliente"),
    crnc: Optional[str] = Query(None, description="Filtro parcial por RNC"),
    ccedula: Optional[str] = Query(None, description="Filtro parcial por cédula"),
    cpasaporte: Optional[str] = Query(None, description="Filtro parcial por pasaporte"),
    estado_formulario: Optional[str] = Query(None, description="Filtro por estado del formulario (VIGENTE, VENCIDO, VENCIDO (NO REMITIDO), PENDIENTE DE REMISIÓN, SIN CLASIFICAR)"),
    username: str = Depends(verify_credentials)
):
    """
    Obtiene información de KYC (Know Your Customer) con formularios y estados.
    
    Filtros disponibles:
    - cnomcliente: Nombre del cliente (búsqueda parcial)
    - crnc: RNC (búsqueda parcial)
    - ccedula: Cédula (búsqueda parcial)
    - cpasaporte: Pasaporte (búsqueda parcial)
    - estado_formulario: Estado del formulario (exacto)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Construir la consulta base
        base_query = """
            SELECT
                RTRIM(c.ccodclien) AS id_client,
                c.icodclien AS cod_client,
                c.inumclient AS num_client,
                RTRIM(c.cnomcliente) AS nombre,
                RTRIM(c.capellidos) AS apellido,
                RTRIM(c.crnc) AS rnc,
                RTRIM(c.cpasaporte) AS pasporrte,
                c.dfechnac AS fecha_nacimiento,
                RTRIM(c.ccedula) AS cedula,
                RTRIM(c.cdirecofi1) AS dirreccion_1,
                RTRIM(c.cdirecofi2) AS dirreccion_2,
                RTRIM(c.cdirecofi3) AS dirreccion_3,
                RTRIM(c.cdireccas1) AS dirreccion_casa_1,
                RTRIM(c.cdireccas2) AS dirreccion_casa_2,
                RTRIM(c.cdireccas3) AS dirreccion_casa_3,
                RTRIM(c.ctipotel1) AS tipo_telefono,
                RTRIM(c.cnumtel1) AS num_telefono,
                RTRIM(c.ctipotel2) AS tipo_celular_1,
                RTRIM(c.cnumtel2) AS num_celular_2,
                RTRIM(c.cemail1) AS email_1,
                RTRIM(c.cemail2) AS email_2,
                c.dfechingreso AS fecha_ingreso,
                c.fechaCreacionCliente AS fecha_creacion_cliente,
                c.fechaCreacionProspecto AS fecha_creacion_prospecto,
                RTRIM(cd.ccodsucursal) AS ccodsucursal,
                cd.fechformremitido AS fecha_remision_formulario,
                cd.fechformrecibido AS fecha_recepcion_formulario,
                cd.fechvencform AS fecha_venc_form,
                cd.formremitido,
                cd.formrecibido,
                CASE
                    WHEN cd.fechformremitido IS NOT NULL 
                         AND cd.fechvencform >= GETDATE() THEN 'VIGENTE'
                    WHEN cd.fechformremitido IS NOT NULL 
                         AND cd.fechvencform < GETDATE() THEN 'VENCIDO'
                    WHEN cd.fechformremitido IS NULL 
                         AND cd.fechvencform < GETDATE() THEN 'VENCIDO (NO REMITIDO)'
                    WHEN cd.fechformremitido IS NULL 
                         AND cd.fechvencform >= GETDATE() THEN 'PENDIENTE DE REMISIÓN'
                    ELSE 'SIN CLASIFICAR'
                END AS estado_formulario,
                DATEDIFF(DAY, GETDATE(), cd.fechvencform) AS dias_hasta_vencimiento
            FROM imclientdet cd
            INNER JOIN imclient c ON c.ccodclien = cd.ccodclien
            WHERE cd.fechvencform IS NOT NULL
              AND cd.fechvencform >= '2020-01-01'
              AND cd.fechvencform <= '2025-12-31'
        """
        
        # Construir condiciones de filtro
        filter_conditions = []
        params = []
        
        if cnomcliente:
            filter_conditions.append("c.cnomcliente LIKE ?")
            params.append(f"%{cnomcliente}%")
        
        if crnc:
            filter_conditions.append("c.crnc LIKE ?")
            params.append(f"%{crnc}%")
        
        if ccedula:
            filter_conditions.append("c.ccedula LIKE ?")
            params.append(f"%{ccedula}%")
        
        if cpasaporte:
            filter_conditions.append("c.cpasaporte LIKE ?")
            params.append(f"%{cpasaporte}%")
        
        # Agregar condiciones de filtro a la consulta
        if filter_conditions:
            base_query += " AND " + " AND ".join(filter_conditions)
        
        # Construir subconsulta para aplicar filtro de estado_formulario (campo calculado)
        subquery = f"SELECT * FROM ({base_query}) as filtered"
        estado_filter_params = []
        
        if estado_formulario:
            subquery += " WHERE estado_formulario = ?"
            estado_filter_params.append(estado_formulario)
        
        # Consulta para calcular totales por estado (sin filtro de estado_formulario)
        totales_query = f"""
            SELECT 
                SUM(CASE WHEN estado_formulario = 'VIGENTE' THEN 1 ELSE 0 END) AS vigente,
                SUM(CASE WHEN estado_formulario = 'VENCIDO' THEN 1 ELSE 0 END) AS vencido,
                SUM(CASE WHEN estado_formulario = 'VENCIDO (NO REMITIDO)' THEN 1 ELSE 0 END) AS vencido_no_remitido,
                SUM(CASE WHEN estado_formulario = 'PENDIENTE DE REMISIÓN' THEN 1 ELSE 0 END) AS pendiente_de_remision,
                SUM(CASE WHEN estado_formulario = 'SIN CLASIFICAR' THEN 1 ELSE 0 END) AS sin_clasificar
            FROM ({base_query}) as filtered
        """
        cursor.execute(totales_query, params)
        totales_row = cursor.fetchone()
        totales = TotalesPorEstado(
            vigente=totales_row[0] or 0,
            vencido=totales_row[1] or 0,
            vencido_no_remitido=totales_row[2] or 0,
            pendiente_de_remision=totales_row[3] or 0,
            sin_clasificar=totales_row[4] or 0
        )
        
        # Consulta para contar el total de registros
        count_query = f"SELECT COUNT(*) as total FROM ({subquery}) as counted"
        count_params = params + estado_filter_params
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]
        
        # Calcular paginación
        total_pages = ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size
        
        # Consulta paginada con ordenamiento
        paginated_query = f"""
            SELECT * FROM (
                {subquery}
            ) as paginated
            ORDER BY fecha_venc_form DESC
            OFFSET ? ROWS
            FETCH NEXT ? ROWS ONLY
        """
        
        params_with_pagination = count_params + [offset, page_size]
        cursor.execute(paginated_query, params_with_pagination)
        
        # Obtener nombres de columnas
        columns = [column[0] for column in cursor.description]
        
        # Obtener resultados
        results = cursor.fetchall()
        
        # Convertir a lista de diccionarios
        data = []
        for row in results:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                # Eliminar espacios en blanco al final de campos de texto
                if value is not None and isinstance(value, str):
                    value = value.rstrip()
                # Convertir None a None explícitamente
                row_dict[col] = value if value is not None else None
            data.append(KYCResponse(**row_dict))
        
        return PaginatedKYCResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            data=data,
            totales_por_estado=totales
        )
        
    except pyodbc.Error as e:
        logger.error(
            f"Error de base de datos en endpoint /api/kyc",
            exc_info=True,
            extra={
                "endpoint": "/api/kyc",
                "error_type": "pyodbc.Error",
                "error_message": str(e),
                "query_params": {
                    "page": page,
                    "page_size": page_size,
                    "cnomcliente": cnomcliente,
                    "crnc": crnc,
                    "ccedula": ccedula,
                    "cpasaporte": cpasaporte,
                    "estado_formulario": estado_formulario
                },
                "traceback": traceback.format_exc()
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error en la base de datos: {str(e)}"
        )
    except Exception as e:
        logger.error(
            f"Error inesperado en endpoint /api/kyc",
            exc_info=True,
            extra={
                "endpoint": "/api/kyc",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query_params": {
                    "page": page,
                    "page_size": page_size,
                    "cnomcliente": cnomcliente,
                    "crnc": crnc,
                    "ccedula": ccedula,
                    "cpasaporte": cpasaporte,
                    "estado_formulario": estado_formulario
                },
                "traceback": traceback.format_exc()
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error inesperado: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@app.get("/api/logs", response_class=JSONResponse)
async def get_logs(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(50, ge=1, le=500, description="Tamaño de página"),
    level: Optional[str] = Query(None, description="Filtro por nivel (ERROR, WARNING, INFO)"),
    endpoint: Optional[str] = Query(None, description="Filtro por endpoint"),
    username: str = Depends(verify_credentials)
):
    """
    Obtiene los logs de la API con paginación y filtros opcionales.
    """
    log_file = "api_errors.log"
    
    if not os.path.exists(log_file):
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "data": []
        }
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Parsear logs
        log_entries = []
        current_entry = {}
        
        for line in lines:
            # Patrón para detectar inicio de nueva entrada de log
            # Formato: YYYY-MM-DD HH:MM:SS,mmm - nombre - LEVEL - mensaje
            log_pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\S+) - (\w+) - (.+)$'
            match = re.match(log_pattern, line.strip())
            
            if match:
                if current_entry:
                    log_entries.append(current_entry)
                timestamp, logger_name, level_name, message = match.groups()
                current_entry = {
                    "timestamp": timestamp,
                    "logger": logger_name,
                    "level": level_name,
                    "message": message,
                    "details": ""
                }
            else:
                # Continuación de la entrada anterior (traceback, etc.)
                if current_entry:
                    current_entry["details"] += line
        
        if current_entry:
            log_entries.append(current_entry)
        
        # Revertir para mostrar los más recientes primero
        log_entries.reverse()
        
        # Aplicar filtros
        filtered_entries = log_entries
        if level:
            filtered_entries = [e for e in filtered_entries if e["level"] == level.upper()]
        if endpoint:
            filtered_entries = [e for e in filtered_entries if endpoint.lower() in e["message"].lower()]
        
        # Paginación
        total = len(filtered_entries)
        total_pages = ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size
        paginated_entries = filtered_entries[offset:offset + page_size]
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": paginated_entries
        }
        
    except Exception as e:
        logger.error(f"Error al leer logs: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al leer los logs: {str(e)}"
        )


@app.get("/logs", response_class=HTMLResponse)
async def view_logs_html(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    level: Optional[str] = Query(None),
    endpoint: Optional[str] = Query(None),
    username: str = Depends(verify_credentials)
):
    """
    Interfaz visual HTML para ver los logs de la API.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Logs de la API - SIA Seguros</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px;
                min-height: 100vh;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .filters {
                padding: 20px;
                background: #f5f5f5;
                border-bottom: 2px solid #e0e0e0;
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                align-items: center;
            }
            .filters input, .filters select, .filters button {
                padding: 10px 15px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
            }
            .filters button {
                background: #667eea;
                color: white;
                border: none;
                cursor: pointer;
                transition: background 0.3s;
            }
            .filters button:hover {
                background: #5568d3;
            }
            .logs-container {
                padding: 20px;
                max-height: 70vh;
                overflow-y: auto;
            }
            .log-entry {
                margin-bottom: 15px;
                padding: 15px;
                border-radius: 5px;
                border-left: 4px solid #ddd;
                background: #f9f9f9;
                transition: transform 0.2s;
            }
            .log-entry:hover {
                transform: translateX(5px);
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .log-entry.ERROR {
                border-left-color: #e74c3c;
                background: #fee;
            }
            .log-entry.WARNING {
                border-left-color: #f39c12;
                background: #fff8e1;
            }
            .log-entry.INFO {
                border-left-color: #3498db;
                background: #e3f2fd;
            }
            .log-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
                flex-wrap: wrap;
                gap: 10px;
            }
            .log-level {
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 12px;
                text-transform: uppercase;
            }
            .log-level.ERROR {
                background: #e74c3c;
                color: white;
            }
            .log-level.WARNING {
                background: #f39c12;
                color: white;
            }
            .log-level.INFO {
                background: #3498db;
                color: white;
            }
            .log-timestamp {
                color: #666;
                font-size: 0.9em;
            }
            .log-message {
                color: #333;
                font-weight: 500;
                margin-bottom: 5px;
            }
            .log-details {
                color: #666;
                font-size: 0.85em;
                font-family: 'Courier New', monospace;
                white-space: pre-wrap;
                background: #f5f5f5;
                padding: 10px;
                border-radius: 3px;
                margin-top: 10px;
                max-height: 200px;
                overflow-y: auto;
            }
            .pagination {
                padding: 20px;
                text-align: center;
                background: #f5f5f5;
                border-top: 2px solid #e0e0e0;
            }
            .pagination button {
                padding: 10px 20px;
                margin: 0 5px;
                border: 1px solid #ddd;
                background: white;
                border-radius: 5px;
                cursor: pointer;
                transition: all 0.3s;
            }
            .pagination button:hover:not(:disabled) {
                background: #667eea;
                color: white;
                border-color: #667eea;
            }
            .pagination button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .pagination span {
                margin: 0 10px;
                color: #666;
            }
            .no-logs {
                text-align: center;
                padding: 40px;
                color: #999;
            }
            .refresh-btn {
                background: #27ae60 !important;
            }
            .refresh-btn:hover {
                background: #229954 !important;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📋 Logs de la API</h1>
                <p>Sistema de monitoreo de errores y eventos</p>
            </div>
            <div class="filters">
                <input type="text" id="endpointFilter" placeholder="Filtrar por endpoint..." value="">
                <select id="levelFilter">
                    <option value="">Todos los niveles</option>
                    <option value="ERROR">ERROR</option>
                    <option value="WARNING">WARNING</option>
                    <option value="INFO">INFO</option>
                </select>
                <input type="number" id="pageSize" placeholder="Registros por página" value="50" min="1" max="500">
                <button onclick="loadLogs(1)">🔍 Filtrar</button>
                <button class="refresh-btn" onclick="loadLogs(currentPage)">🔄 Actualizar</button>
            </div>
            <div class="logs-container" id="logsContainer">
                <div class="no-logs">Cargando logs...</div>
            </div>
            <div class="pagination" id="pagination"></div>
        </div>
        <script>
            let currentPage = 1;
            let totalPages = 1;
            
            async function loadLogs(page = 1) {
                currentPage = page;
                const level = document.getElementById('levelFilter').value;
                const endpoint = document.getElementById('endpointFilter').value;
                const pageSize = document.getElementById('pageSize').value || 50;
                
                const params = new URLSearchParams({
                    page: page,
                    page_size: pageSize
                });
                if (level) params.append('level', level);
                if (endpoint) params.append('endpoint', endpoint);
                
                try {
                    const response = await fetch(`/api/logs?${params.toString()}`, {
                        headers: {
                            'Authorization': 'Basic ' + btoa('Admin:Caramelo#2030')
                        }
                    });
                    const data = await response.json();
                    
                    totalPages = data.total_pages;
                    displayLogs(data.data);
                    updatePagination(data.page, data.total_pages, data.total);
                } catch (error) {
                    document.getElementById('logsContainer').innerHTML = 
                        '<div class="no-logs">Error al cargar los logs: ' + error.message + '</div>';
                }
            }
            
            function displayLogs(logs) {
                const container = document.getElementById('logsContainer');
                
                if (logs.length === 0) {
                    container.innerHTML = '<div class="no-logs">No hay logs disponibles</div>';
                    return;
                }
                
                container.innerHTML = logs.map(log => `
                    <div class="log-entry ${log.level}">
                        <div class="log-header">
                            <span class="log-timestamp">${log.timestamp}</span>
                            <span class="log-level ${log.level}">${log.level}</span>
                        </div>
                        <div class="log-message">${escapeHtml(log.message)}</div>
                        ${log.details ? '<div class="log-details">' + escapeHtml(log.details) + '</div>' : ''}
                    </div>
                `).join('');
            }
            
            function updatePagination(page, totalPages, total) {
                const pagination = document.getElementById('pagination');
                pagination.innerHTML = `
                    <button onclick="loadLogs(${page - 1})" ${page === 1 ? 'disabled' : ''}>← Anterior</button>
                    <span>Página ${page} de ${totalPages} (Total: ${total} registros)</span>
                    <button onclick="loadLogs(${page + 1})" ${page === totalPages ? 'disabled' : ''}>Siguiente →</button>
                `;
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            // Cargar logs al iniciar
            loadLogs(1);
            
            // Auto-refresh cada 30 segundos
            setInterval(() => loadLogs(currentPage), 30000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)

