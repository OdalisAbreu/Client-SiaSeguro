from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional
from math import ceil
import logging
import traceback
from config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from models.ejecutivo import EjecutivoCuentaRow, PaginatedEjecutivoCuentaResponse
from auth import verify_credentials
from database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter()

ENDPOINT = "/ejecutivos"

AREAS_VALIDAS = (
    "Riesgos de Personas",
    "Riesgos Generales",
    "Riesgos Internacionales",
    "Transversal (Cobros/Gestión)",
)

DESC_NOMBRE = "Filtro parcial por nombre completo del ejecutivo (nombres + apellidos), sin distinguir mayúsculas"
DESC_ES_EMPLEADO = "Filtro por tipo. 1 = empleados (esEmpleado = 1), 0 = no empleados (externos/agentes), en blanco = todos"
DESC_AREA = "Filtro por área (exacto). Valores: " + ", ".join(AREAS_VALIDAS)

# Área calculada a partir del tipo de ejecutivo (imtipejec.ccodtipejec).
# ELSE: 002 Analista de Cobros y Comisiones, 003 Gestor.
AREA_CASE = """
    CASE t.ccodtipejec
        WHEN '006'      THEN 'Riesgos de Personas'
        WHEN '00000001' THEN 'Riesgos Generales'
        WHEN '00000003' THEN 'Riesgos Internacionales'
        WHEN '00000018' THEN 'Riesgos Generales'
        WHEN '00000019' THEN 'Riesgos Generales'
        WHEN '00000017' THEN 'Riesgos Generales'
        WHEN '00000004' THEN 'Riesgos Internacionales'
        WHEN '00000002' THEN 'Riesgos Generales'
        WHEN '004'      THEN 'Riesgos de Personas'
        WHEN '00000005' THEN 'Riesgos Generales'
        WHEN '00000009' THEN 'Riesgos Internacionales'
        WHEN '001'      THEN 'Riesgos de Personas'
        ELSE 'Transversal (Cobros/Gestión)'
    END
"""


@router.get(ENDPOINT, response_model=PaginatedEjecutivoCuentaResponse, tags=["Ejecutivos"])
async def get_ejecutivos(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Tamaño de página"),
    nombre: Optional[str] = Query(None, description=DESC_NOMBRE),
    es_empleado: Optional[str] = Query(None, description=DESC_ES_EMPLEADO),
    area: Optional[str] = Query(None, description=DESC_AREA),
    username: str = Depends(verify_credentials)
):
    """
    Obtiene los ejecutivos de cuenta activos (imejecut.cestatus = 'A') por rol,
    con la cantidad de clientes que tienen asignados activamente
    (imcliejec.tfechanulo IS NULL). Una fila por ejecutivo y rol.

    Filtros:
    - nombre: nombre completo del ejecutivo (búsqueda parcial, sin distinguir mayúsculas)
    - es_empleado: 1 = empleados, 0 = no empleados, en blanco = todos
    - area: Riesgos de Personas, Riesgos Generales, Riesgos Internacionales,
      Transversal (Cobros/Gestión)
    """
    query_params_log = {
        "page": page, "page_size": page_size, "nombre": nombre,
        "es_empleado": es_empleado, "area": area,
    }
    conn = None
    try:
        # Normalizar el filtro de empleado: 1 = empleados, 0 = no empleados, en blanco = todos
        empleado_flag: Optional[int] = None
        if es_empleado is not None and es_empleado.strip() != "":
            valor = es_empleado.strip()
            if valor in ("1", "0"):
                empleado_flag = int(valor)
            else:
                raise HTTPException(
                    status_code=422,
                    detail="Valor inválido para 'es_empleado'. Use 1 (empleados), 0 (no empleados) o déjelo en blanco."
                )

        conn = get_db_connection()
        conn.timeout = 30
        cursor = conn.cursor()

        where = " WHERE ce.tfechanulo IS NULL AND e.cestatus = ?"
        params = ["A"]

        if nombre and nombre.strip():
            # imejecut usa collation CS; se compara con la collation CI de la base
            where += (
                " AND (RTRIM(e.cnombres) + ' ' + RTRIM(e.capellidos))"
                " COLLATE DATABASE_DEFAULT LIKE ? COLLATE DATABASE_DEFAULT"
            )
            params.append(f"%{nombre.strip()}%")

        if empleado_flag is not None:
            where += " AND e.esEmpleado = ?"
            params.append(empleado_flag)

        # Query agrupado en subconsulta para poder filtrar por el área calculada
        base_query = f"""
            SELECT * FROM (
                SELECT
                    RTRIM(e.ccodejecut)                             AS cod_ejecutivo,
                    {AREA_CASE}                                     AS area,
                    RTRIM(t.ccodtipejec)                            AS cod_rol,
                    RTRIM(t.cdescripcion)                           AS rol,
                    RTRIM(e.cnombres) + ' ' + RTRIM(e.capellidos)   AS ejecutivo,
                    RTRIM(e.cestatus)                               AS estatus,
                    e.esEmpleado                                    AS es_empleado,
                    COUNT(DISTINCT ce.ccodclien)                    AS cantidad_clientes_asignados
                FROM imcliejec ce
                JOIN imtipejec t ON t.ccodtipejec = ce.ccodtipejec
                JOIN imejecut e  ON e.ccodejecut  = ce.ccodejecut
                {where}
                GROUP BY
                    e.ccodejecut, t.ccodtipejec, t.cdescripcion,
                    e.cnombres, e.capellidos, e.cestatus, e.esEmpleado
            ) AS ejec
        """

        if area and area.strip():
            base_query += " WHERE ejec.area = ?"
            params.append(area.strip())

        # Contar el total de registros
        count_query = f"SELECT COUNT(*) AS total FROM ({base_query}) AS filtered"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # Calcular paginación
        total_pages = ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size

        paginated_query = f"""
            {base_query}
            ORDER BY area, ejecutivo, cod_ejecutivo, cod_rol
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
            data.append(EjecutivoCuentaRow(**row_dict))

        return PaginatedEjecutivoCuentaResponse(
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
            f"Error consultando ejecutivos en endpoint {ENDPOINT}",
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
        raise HTTPException(status_code=500, detail="Error al consultar los ejecutivos de cuenta.")
    finally:
        if conn:
            conn.close()
