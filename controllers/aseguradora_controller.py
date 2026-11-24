from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional, Literal
from math import ceil
import logging
import traceback
from config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from models.aseguradora import (
    AseguradoraRow,
    PaginatedAseguradoraResponse,
    AseguradoraRamoRow,
    PaginatedAseguradoraRamoResponse,
)
from auth import verify_credentials
from database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter()

ENDPOINT = "/aseguradoras"
ENDPOINT_RAMOS = "/aseguradoras/ramos"

DESC_NOMBRE = (
    "Filtro parcial por nombre (cnombre) o siglas (csiglas) de la aseguradora, "
    "sin distinguir mayúsculas"
)
DESC_ESTADO = (
    "Filtro por código de estatus (cestatus, exacto). Valores: "
    "A = Activa, I = Inactiva (se devuelve el código 'I'). En blanco = todas"
)


@router.get(ENDPOINT, response_model=PaginatedAseguradoraResponse, tags=["Aseguradoras"])
async def get_aseguradoras(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Tamaño de página"),
    nombre: Optional[str] = Query(None, description=DESC_NOMBRE),
    estado: Optional[Literal["A", "I"]] = Query(None, description=DESC_ESTADO),
    username: str = Depends(verify_credentials)
):
    """
    Obtiene las aseguradoras (imciaseg) con datos de contacto, estatus y la cantidad
    de pólizas asociadas (impoliza). total_polizas cuenta todas las filas de impoliza,
    incluidas todas las versiones de cada póliza.

    Filtros:
    - nombre: nombre o siglas de la aseguradora (búsqueda parcial, sin distinguir mayúsculas)
    - estado: A = Activa, I = Inactiva, en blanco = todas
    """
    query_params_log = {
        "page": page, "page_size": page_size, "nombre": nombre, "estado": estado,
    }
    conn = None
    try:
        conn = get_db_connection()
        conn.timeout = 30
        cursor = conn.cursor()

        where = ""
        conditions = []
        params = []

        if nombre and nombre.strip():
            # imciaseg usa collation CS; se compara con la collation CI de la base
            conditions.append(
                "(a.cnombre COLLATE DATABASE_DEFAULT LIKE ? COLLATE DATABASE_DEFAULT"
                " OR a.csiglas COLLATE DATABASE_DEFAULT LIKE ? COLLATE DATABASE_DEFAULT)"
            )
            patron = f"%{nombre.strip()}%"
            params.extend([patron, patron])

        if estado is not None:
            conditions.append("a.cestatus = ?")
            params.append(estado)

        if conditions:
            where = " WHERE " + " AND ".join(conditions)

        base_query = f"""
            SELECT
                RTRIM(a.ccodciaseg)                                                 AS codigo,
                RTRIM(a.csiglas)                                                    AS siglas,
                RTRIM(a.cnombre)                                                    AS nombre,
                CASE a.cestatus WHEN 'A' THEN 'Activa' ELSE RTRIM(a.cestatus) END   AS estatus,
                RTRIM(a.crnc)                                                       AS rnc,
                RTRIM(a.cemail)                                                     AS email,
                RTRIM(a.cnumtel1)                                                   AS telefono,
                RTRIM(a.catencion)                                                  AS atencion,
                a.codIntermediario                                                  AS cod_intermediario,
                COUNT(p.ccodpoliza)                                                 AS total_polizas
            FROM imciaseg a
            LEFT JOIN impoliza p ON p.ccodciaseg = a.ccodciaseg
            {where}
            GROUP BY a.ccodciaseg, a.csiglas, a.cnombre, a.cestatus, a.crnc, a.cemail,
                     a.cnumtel1, a.catencion, a.codIntermediario
        """

        # Contar el total de registros
        count_query = f"SELECT COUNT(*) AS total FROM imciaseg a{where}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # Calcular paginación
        total_pages = ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size

        paginated_query = f"""
            {base_query}
            ORDER BY siglas, codigo
            OFFSET ? ROWS
            FETCH NEXT ? ROWS ONLY
        """
        cursor.execute(paginated_query, params + [offset, page_size])

        columns = [column[0] for column in cursor.description]
        data = []
        for row in cursor.fetchall():
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                if value is not None and isinstance(value, str):
                    value = value.strip()
                row_dict[col] = value
            data.append(AseguradoraRow(**row_dict))

        return PaginatedAseguradoraResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            data=data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error consultando aseguradoras en endpoint {ENDPOINT}",
            exc_info=True,
            extra={
                "endpoint": ENDPOINT,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query_params": query_params_log,
                "traceback": traceback.format_exc(),
            },
        )
        # No se exponen detalles de la base de datos al cliente
        raise HTTPException(status_code=500, detail="Error al consultar las aseguradoras.")
    finally:
        if conn:
            conn.close()


@router.get(
    ENDPOINT_RAMOS,
    response_model=PaginatedAseguradoraRamoResponse,
    tags=["Aseguradoras"],
    summary="Ramos por aseguradora",
)
async def get_aseguradoras_ramos(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Tamaño de página"),
    aseguradora: Optional[str] = Query(
        None, description="Filtro parcial por siglas de la aseguradora (csiglas), sin distinguir mayúsculas. En blanco = todas"
    ),
    username: str = Depends(verify_credentials)
):
    """
    Obtiene la cantidad de pólizas por aseguradora, ramo y subramo, y cuántas están
    vigentes (dfinvigenc >= hoy). Una fila por aseguradora (código), ramo y subramo.
    Los conteos incluyen todas las filas de impoliza (todas las versiones de cada póliza).

    Filtros:
    - aseguradora: siglas de la aseguradora (búsqueda parcial, sin distinguir mayúsculas)
    """
    query_params_log = {"page": page, "page_size": page_size, "aseguradora": aseguradora}
    conn = None
    try:
        conn = get_db_connection()
        conn.timeout = 30
        cursor = conn.cursor()

        where = ""
        params = []
        if aseguradora and aseguradora.strip():
            # imciaseg usa collation CS; se compara con la collation CI de la base
            where = " WHERE a.csiglas COLLATE DATABASE_DEFAULT LIKE ? COLLATE DATABASE_DEFAULT"
            params.append(f"%{aseguradora.strip()}%")

        base_query = f"""
            SELECT
                RTRIM(a.ccodciaseg)     AS cod_aseguradora,
                RTRIM(a.csiglas)        AS aseguradora,
                RTRIM(r.cdescripcion)   AS ramo,
                RTRIM(s.cdescripcion)   AS sub_ramo,
                COUNT(*)                AS total_polizas,
                SUM(CASE WHEN p.dfinvigenc >= CAST(GETDATE() AS date) THEN 1 ELSE 0 END) AS polizas_vigentes
            FROM impoliza p
            JOIN imciaseg a      ON a.ccodciaseg = p.ccodciaseg
            JOIN imsubram s      ON s.ccodsubram = p.ccodsubram
            LEFT JOIN imramos r  ON r.ccodramo   = s.ccodramo
            {where}
            GROUP BY a.ccodciaseg, a.csiglas, r.cdescripcion, s.cdescripcion
        """

        # Contar el total de registros
        count_query = f"SELECT COUNT(*) AS total FROM ({base_query}) AS filtered"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # Calcular paginación
        total_pages = ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size

        paginated_query = f"""
            {base_query}
            ORDER BY aseguradora, ramo, sub_ramo, cod_aseguradora
            OFFSET ? ROWS
            FETCH NEXT ? ROWS ONLY
        """
        cursor.execute(paginated_query, params + [offset, page_size])

        columns = [column[0] for column in cursor.description]
        data = []
        for row in cursor.fetchall():
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                if value is not None and isinstance(value, str):
                    value = value.strip()
                row_dict[col] = value
            data.append(AseguradoraRamoRow(**row_dict))

        return PaginatedAseguradoraRamoResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            data=data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error consultando ramos por aseguradora en endpoint {ENDPOINT_RAMOS}",
            exc_info=True,
            extra={
                "endpoint": ENDPOINT_RAMOS,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query_params": query_params_log,
                "traceback": traceback.format_exc(),
            },
        )
        # No se exponen detalles de la base de datos al cliente
        raise HTTPException(status_code=500, detail="Error al consultar los ramos por aseguradora.")
    finally:
        if conn:
            conn.close()
