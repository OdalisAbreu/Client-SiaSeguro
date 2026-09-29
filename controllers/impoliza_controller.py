from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional
from math import ceil
import pyodbc
import logging
import traceback
from config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from models.impoliza import ImPoliza, PaginatedImPolizaResponse
from auth import verify_credentials
from database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter()


POLIZA_ESTADO_ACTIVA = "00000001"


@router.get("/polizas", response_model=PaginatedImPolizaResponse, tags=["Polizas"])
async def get_impolizas(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Tamaño de página"),
    activa: Optional[str] = Query(
        None,
        description="Filtro por estado. 1 = activas (ccodpolsta = '00000001'), "
                    "0 = no activas (ccodpolsta <> '00000001'), en blanco = todas"
    ),
    ccodclien: Optional[str] = Query(None, description="Filtro por código de cliente (exacto)"),
    cnumpoliza: Optional[str] = Query(None, description="Filtro parcial por número de póliza"),
    username: str = Depends(verify_credentials)
):
    """
    Obtiene todos los campos de la tabla impoliza con paginación.
    Solo devuelve la versión actual de cada póliza (lversionactual = 1).

    Filtros:
    - activa: 1 = activas (ccodpolsta = '00000001'), 0 = no activas, en blanco = todas
    - ccodclien: código de cliente (exacto)
    - cnumpoliza: número de póliza (búsqueda parcial)
    """
    conn = None
    try:
        # Normalizar el filtro de estado: 1 = activas, 0 = no activas, en blanco = todas
        activa_flag: Optional[bool] = None
        if activa is not None and activa.strip() != "":
            valor = activa.strip()
            if valor == "1":
                activa_flag = True
            elif valor == "0":
                activa_flag = False
            else:
                raise HTTPException(
                    status_code=422,
                    detail="Valor inválido para 'activa'. Use 1 (activas), 0 (no activas) o déjelo en blanco."
                )

        conn = get_db_connection()
        conn.timeout = 30
        cursor = conn.cursor()

        # Solo la versión actual de cada póliza
        base_query = "SELECT * FROM impoliza WHERE lversionactual = 1"
        params = []

        if activa_flag is not None:
            if activa_flag:
                base_query += " AND ccodpolsta = ?"
                params.append(POLIZA_ESTADO_ACTIVA)
            else:
                base_query += " AND ccodpolsta <> ?"
                params.append(POLIZA_ESTADO_ACTIVA)

        if ccodclien:
            base_query += " AND ccodclien = ?"
            params.append(ccodclien)

        if cnumpoliza:
            base_query += " AND cnumpoliza LIKE ?"
            params.append(f"%{cnumpoliza}%")

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
            ORDER BY ccodpoliza
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
            data.append(ImPoliza(**row_dict))

        return PaginatedImPolizaResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            data=data
        )

    except pyodbc.Error as e:
        logger.error(
            "Error de base de datos en endpoint /polizas",
            exc_info=True,
            extra={
                "endpoint": "/polizas",
                "error_type": "pyodbc.Error",
                "error_message": str(e),
                "query_params": {"page": page, "page_size": page_size, "activa": activa, "ccodclien": ccodclien, "cnumpoliza": cnumpoliza},
                "traceback": traceback.format_exc()
            }
        )
        raise HTTPException(status_code=500, detail=f"Error en la base de datos: {str(e)}")
    except Exception as e:
        logger.error(
            "Error inesperado en endpoint /polizas",
            exc_info=True,
            extra={
                "endpoint": "/polizas",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query_params": {"page": page, "page_size": page_size, "activa": activa, "ccodclien": ccodclien, "cnumpoliza": cnumpoliza},
                "traceback": traceback.format_exc()
            }
        )
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")
    finally:
        if conn:
            conn.close()
