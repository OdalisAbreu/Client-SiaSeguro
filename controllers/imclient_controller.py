from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional
from math import ceil
import pyodbc
import logging
import traceback
from config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from models.imclient import ImClientConTipo, PaginatedImClientConTipoResponse
from auth import verify_credentials
from database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/clientes", response_model=PaginatedImClientConTipoResponse, tags=["Clientes"])
async def get_imclientes(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Tamaño de página"),
    activo: Optional[str] = Query(
        None,
        description="Filtro por estado. 1 = activos (cstatus = 'A'), 0 = inactivos (cstatus <> 'A'), en blanco = todos"
    ),
    cnomcliente: Optional[str] = Query(None, description="Filtro parcial por nombre del cliente"),
    tipo_cliente: Optional[str] = Query(
        None,
        description="Filtro por tipo de cliente (exacto). Valores: PERSONAL, COMERCIAL, "
                    "BANCASEGUROS, PERSONALES PREMIUM, CORPORATIVOS, GUBERNAMENTALES"
    ),
    sucursal: Optional[str] = Query(
        None,
        description="Filtro por sucursal (exacto, por nombre). Valores: Principal, Romana, Punta Cana"
    ),
    username: str = Depends(verify_credentials)
):
    """
    Obtiene todos los campos de la tabla imclient con paginación, incluyendo
    el tipo de cliente (imtipclient) y la sucursal (imsucursal), ambos
    obtenidos a través de imclientdet.

    Filtros:
    - activo: 1 = activos (cstatus = 'A'), 0 = inactivos, en blanco = todos
    - cnomcliente: nombre del cliente (búsqueda parcial)
    - tipo_cliente: tipo de cliente (exacto)
    - sucursal: nombre de la sucursal (exacto)
    """
    conn = None
    try:
        # Normalizar el filtro de estado: 1 = activos, 0 = inactivos, en blanco = todos
        activo_flag: Optional[bool] = None
        if activo is not None and activo.strip() != "":
            valor = activo.strip()
            if valor == "1":
                activo_flag = True
            elif valor == "0":
                activo_flag = False
            else:
                raise HTTPException(
                    status_code=422,
                    detail="Valor inválido para 'activo'. Use 1 (activos), 0 (inactivos) o déjelo en blanco."
                )

        conn = get_db_connection()
        conn.timeout = 30
        cursor = conn.cursor()

        # Ni el tipo de cliente ni la sucursal estan en imclient: se obtienen
        # encadenando imclient -> imclientdet -> imtipclient / imsucursal.
        # Se usa LEFT JOIN para no perder clientes sin detalle, sin tipo
        # o sin sucursal asignada.
        base_query = """
            SELECT
                c.*,
                cd.imtipclientid AS imtipclientid,
                RTRIM(tc.tipo) AS tipo_cliente,
                RTRIM(cd.ccodsucursal) AS ccodsucursal,
                RTRIM(s.cdescripcion) AS sucursal
            FROM imclient c
            LEFT JOIN imclientdet cd ON cd.ccodclien = c.ccodclien
            LEFT JOIN imtipclient tc ON tc.imtipclientid = cd.imtipclientid
            LEFT JOIN imsucursal s ON s.ccodsucursal = cd.ccodsucursal
            WHERE 1=1
        """
        params = []

        if activo_flag is not None:
            if activo_flag:
                base_query += " AND c.cstatus = ?"
                params.append("A")
            else:
                base_query += " AND c.cstatus <> ?"
                params.append("A")

        if cnomcliente:
            base_query += " AND c.cnomcliente LIKE ?"
            params.append(f"%{cnomcliente}%")

        if tipo_cliente:
            base_query += " AND RTRIM(tc.tipo) = ?"
            params.append(tipo_cliente.strip())

        if sucursal:
            base_query += " AND RTRIM(s.cdescripcion) = ?"
            params.append(sucursal.strip())

        # Contar el total de registros
        count_query = f"SELECT COUNT(*) AS total FROM ({base_query}) AS filtered"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # Calcular paginación
        total_pages = ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size

        paginated_query = f"""
            SELECT * FROM (
                {base_query}
            ) AS filtered
            ORDER BY ccodclien
            OFFSET ? ROWS
            FETCH NEXT ? ROWS ONLY
        """
        cursor.execute(paginated_query, params + [offset, page_size])

        columns = [column[0] for column in cursor.description]
        results = cursor.fetchall()

        data = []
        for row in results:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                if value is not None and isinstance(value, str):
                    value = value.rstrip()
                row_dict[col] = value
            data.append(ImClientConTipo(**row_dict))

        return PaginatedImClientConTipoResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            data=data
        )

    except pyodbc.Error as e:
        logger.error(
            "Error de base de datos en endpoint /clientes",
            exc_info=True,
            extra={
                "endpoint": "/clientes",
                "error_type": "pyodbc.Error",
                "error_message": str(e),
                "query_params": {"page": page, "page_size": page_size, "activo": activo, "cnomcliente": cnomcliente, "tipo_cliente": tipo_cliente, "sucursal": sucursal},
                "traceback": traceback.format_exc()
            }
        )
        raise HTTPException(status_code=500, detail=f"Error en la base de datos: {str(e)}")
    except Exception as e:
        logger.error(
            "Error inesperado en endpoint /clientes",
            exc_info=True,
            extra={
                "endpoint": "/clientes",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query_params": {"page": page, "page_size": page_size, "activo": activo, "cnomcliente": cnomcliente, "tipo_cliente": tipo_cliente, "sucursal": sucursal},
                "traceback": traceback.format_exc()
            }
        )
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")
    finally:
        if conn:
            conn.close()
