from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from math import ceil
import pyodbc
from config import (
    TARGET_SERVER, TARGET_DATABASE, TARGET_USER, TARGET_PASSWORD,
    DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
)
from models import ClientResponse, PaginatedResponse, KYCResponse, PaginatedKYCResponse, TotalesPorEstado
from auth import verify_credentials

app = FastAPI(
    title="API SIA Seguros - Clientes",
    description="API para consultar información de clientes desde SQL Server",
    version="1.0.0"
)


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
        raise HTTPException(
            status_code=500,
            detail=f"Error en la base de datos: {str(e)}"
        )
    except Exception as e:
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
        raise HTTPException(
            status_code=500,
            detail=f"Error en la base de datos: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error inesperado: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)

