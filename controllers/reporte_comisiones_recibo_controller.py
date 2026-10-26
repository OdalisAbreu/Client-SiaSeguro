"""
Reporte de Comisiones Generadas Asociadas a Pólizas - Recibo Multi Vendor.

Grano: una fila por recibo aplicado a factura (imrecpol) x coaseguradora
(imfactcoaseg). Si la factura no tiene coaseguro declarado, sale una sola fila
con la aseguradora líder de la póliza al 100%.

Estructura:
1. Query principal (SQL de referencia validado) con todo lo verificado.
2. agente_poliza / porcentaje_incentivo_agente: se resuelven aparte, solo para
   las pólizas de la página, en una función aislada (ver "CAMPO NO VALIDADO").
"""
from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional, Iterable
from datetime import date, timedelta
from decimal import Decimal
import logging
import traceback
from models.reporte_comisiones_recibo import (
    ReporteComisionesReciboRow,
    ReporteComisionesReciboFiltros,
    ReporteComisionesReciboResponse,
    ADVERTENCIA_AGENTE_NO_VALIDADO,
)
from auth import verify_credentials
from database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

ENDPOINT = "/api/reportes/comisiones-recibo-multivendor"
QUERY_TIMEOUT_SECONDS = 120
# SQL Server admite hasta 2100 parámetros por query; se trocean las listas IN.
IN_CHUNK_SIZE = 1000

# Expansión "Multi Vendor": coaseguradoras declaradas en la factura o, si no
# hay ninguna, la aseguradora líder de la póliza al 100%.
COASEG_CTE = """
WITH Coaseg AS (
    SELECT fc.ccodfact, fc.ccodciaseg, fc.nporcpart
    FROM dbo.imfactcoaseg fc
    UNION ALL
    SELECT f2.ccodfact, pol2.ccodciaseg, CAST(100.00 AS numeric(18,2))
    FROM dbo.imfact f2
    JOIN dbo.impoliza pol2 ON pol2.ccodpoliza = f2.ccodpoliza
    WHERE NOT EXISTS (SELECT 1 FROM dbo.imfactcoaseg fc2 WHERE fc2.ccodfact = f2.ccodfact)
)
"""

FROM_WHERE = """
FROM dbo.imrecpol rp
JOIN dbo.imrecibo r            ON r.ccodrecibo     = rp.ccodrecibo
JOIN dbo.imfact f              ON f.ccodfact       = rp.ccodfact
JOIN dbo.impoliza pol          ON pol.ccodpoliza   = f.ccodpoliza
JOIN Coaseg cs                 ON cs.ccodfact      = f.ccodfact
JOIN dbo.imciaseg caseg        ON caseg.ccodciaseg = cs.ccodciaseg
JOIN dbo.imciaseg aseg         ON aseg.ccodciaseg  = pol.ccodciaseg
JOIN dbo.imclient cli          ON cli.ccodclien    = pol.ccodclien
LEFT JOIN dbo.imclient g       ON g.ccodclien      = cli.ccodgrupo
LEFT JOIN dbo.imclientdet cdet ON cdet.ccodclien   = cli.ccodclien
LEFT JOIN dbo.imsucursal suc   ON suc.ccodsucursal = cdet.ccodsucursal
LEFT JOIN dbo.imtipclient tc   ON tc.imtipclientid = cdet.imtipclientid
JOIN dbo.imsubram sub          ON sub.ccodsubram   = pol.ccodsubram
JOIN dbo.imramos ramo          ON ramo.ccodramo    = sub.ccodramo
LEFT JOIN dbo.imareram ar      ON ar.ccodsubram    = sub.ccodsubram
LEFT JOIN dbo.imarea area      ON area.ccodarea    = ar.ccodarea
LEFT JOIN dbo.imfaconc conc    ON conc.ccodfaconc  = f.ccodfaconc
LEFT JOIN dbo.imfaconc rconc   ON rconc.ccodfaconc = r.ccodfaconc
LEFT JOIN dbo.imfrmpag frmpag  ON frmpag.ccodfrmpag = r.ccodfrmpag
WHERE r.lanulado = 0
  -- Rango de días completos: dfechrecibo trae hora, por eso "< fecha_hasta + 1 día"
  -- y nunca BETWEEN (descartaría casi todos los recibos del último día).
  AND (   (r.dfechrecibo     >= ? AND r.dfechrecibo     < ?)
       OR (f.dfechcierreprod >= ? AND f.dfechcierreprod < ?))
"""

# Las columnas con prefijo "_" son internas y no se exponen en la respuesta.
SELECT_COLUMNS = """
SELECT
    cli.inumclient                                        AS cod_cliente,
    RTRIM(cli.cnomcliente)                                AS cliente,
    RTRIM(ISNULL(g.cnomcliente, cli.cnomcliente))         AS grupo_deudor,
    RTRIM(suc.cdescripcion)                               AS sucursal,
    RTRIM(tc.tipo)                                        AS tipo_cliente,
    cli.dfechingreso                                      AS fecha_cliente,
    RTRIM(area.cdescripcion)                              AS area,
    RTRIM(ramo.cdescripcion)                              AS ramo,
    pol.dfechemis                                         AS fecha_emision,
    RTRIM(pol.cnumpoliza)                                 AS poliza,
    RTRIM(aseg.cnombre)                                   AS aseguradora,
    RTRIM(caseg.cnombre)                                  AS coaseguro,
    cs.nporcpart                                          AS porcentaje_participacion,
    RTRIM(pol.cmoneda)                                    AS moneda,
    RTRIM(r.cnumrecprov)                                  AS recibo,
    RTRIM(rconc.cdescripcion)                             AS concepto_recibo,
    RTRIM(frmpag.cdescripcion)                            AS forma_pago,
    r.dfechrecibo                                         AS fecha_recibo,
    r.tfechregistro                                       AS fecha_registro,
    RTRIM(f.cnumfact)                                     AS factura,
    f.dinivigen                                           AS inicio_vig_factura,
    DATEDIFF(DAY, f.dinivigen, r.dfechrecibo)             AS dias,
    RTRIM(conc.cdescripcion)                              AS concepto,
    f.ygadministrativo                                    AS gastos_admin,
    f.yprimabruta                                         AS prima_bruta,
    f.yprimaneta                                          AS prima_neta,
    (CASE WHEN pol.mantenerporcomis = 1 THEN 'Si' ELSE '' END) AS mantiene_porcentaje_comis,
    (SELECT TOP 1 ri.inumrecing FROM dbo.imrecing ri WHERE ri.ccodrecing = rp.ccodrecing)
                                                          AS recibo_comisiones,
    rp.bporcomis                                          AS porcentaje_comis,
    ROUND(rp.yaplicado * rp.bporcomis / 100.0, 2)         AS comision_generada,
    rp.ycomisrecibida                                     AS comision_liquidada,
    ROUND(rp.yaplicado * rp.bporcomis / 100.0, 2) - rp.ycomisrecibida
                                                          AS diferencia,
    rp.ysobrecomision                                     AS porcentaje_sobrecomis,
    ROUND(rp.yaplicado * rp.ysobrecomision / 100.0, 2)    AS sobrecomis_generada,
    (CASE WHEN rp.bporcomis <> 0
          THEN rp.ycomisrecibida * (rp.ysobrecomision / rp.bporcomis)
          ELSE rp.yaplicado * (pol.ysobrecomision / 100.0)
     END)                                                 AS sobrecomis_liquidada,
    (ROUND(rp.yaplicado * rp.ysobrecomision / 100.0, 2)
     - (CASE WHEN rp.bporcomis <> 0
             THEN rp.ycomisrecibida * (rp.ysobrecomision / rp.bporcomis)
             ELSE rp.yaplicado * (pol.ysobrecomision / 100.0)
        END))                                             AS sobrecomis_diferencia,
    pol.ccodpoliza                                        AS _ccodpoliza
"""

# Desempates (ccodrecpol, coaseguradora) para que la paginación sea estable
ORDER_BY = " ORDER BY cli.inumclient, r.dfechrecibo, f.cnumfact, rp.ccodrecpol, cs.ccodciaseg"


def _chunks(values: list, size: int = IN_CHUNK_SIZE) -> Iterable[list]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


# ---------------------------------------------------------------------------
# CAMPO NO VALIDADO: agente_poliza / porcentaje_incentivo_agente
# TODO(reporte-comisiones): fuente no confirmada. Hoy usa imcocorretaje +
# cocorredores (ambas vacías en el ambiente validado, así que sale null / 0).
# Cuando se confirme que vw_Comis_Generada (sobre ST_ProPago) tiene datos en
# producción, reemplazar SOLO esta función por la lectura de su columna Agente;
# el resto del endpoint no depende de cómo se resuelve.
# ---------------------------------------------------------------------------

def _resolver_agente_poliza(cursor, ccodpolizas: list[str]) -> tuple[dict[str, tuple[Optional[str], Decimal]], Optional[str]]:
    """
    Devuelve ({ccodpoliza: (agente, porcentaje)}, agente_default).
    Misma fórmula que el SQL de referencia: el corredor de mayor nporcpart de
    la póliza; si no hay, el corredor con cdefault = 1 y porcentaje 0.
    """
    por_poliza: dict[str, tuple[Optional[str], Decimal]] = {}
    for chunk in _chunks(ccodpolizas):
        cursor.execute(
            f"""
            SELECT ic.ccodpoliza, RTRIM(cor.cnombre), ic.nporcpart
            FROM dbo.imcocorretaje ic
            LEFT JOIN dbo.cocorredores cor ON cor.ccodcorredor = ic.ccodcorredor
            WHERE ic.ccodpoliza IN ({", ".join(["?"] * len(chunk))})
            ORDER BY ic.ccodpoliza, ic.nporcpart DESC
            """,
            chunk,
        )
        for ccodpoliza, nombre, porc in cursor.fetchall():
            # Por el ORDER BY, el primero de cada póliza es el de mayor participación
            por_poliza.setdefault(ccodpoliza, (nombre, porc))

    cursor.execute("SELECT TOP 1 RTRIM(cnombre) FROM dbo.cocorredores WHERE cdefault = 1")
    row = cursor.fetchone()
    agente_default = row[0] if row else None
    return por_poliza, agente_default


def _aplicar_agente_poliza(cursor, filas: list[dict]) -> None:
    ccodpolizas = sorted({f["_ccodpoliza"] for f in filas if f["_ccodpoliza"]})
    por_poliza, agente_default = _resolver_agente_poliza(cursor, ccodpolizas)
    for fila in filas:
        nombre, porc = por_poliza.get(fila["_ccodpoliza"], (None, None))
        # Igual que el ISNULL del SQL de referencia, campo por campo
        fila["agente_poliza"] = nombre if nombre is not None else agente_default
        fila["porcentaje_incentivo_agente"] = porc if porc is not None else Decimal("0")

# --------------------- fin CAMPO NO VALIDADO -------------------------------


EJEMPLO_RESPUESTA = {
    "total": 228,
    "filtros": {"fecha_desde": "2026-09-30", "fecha_hasta": "2026-09-30", "cliente": None, "limit": 1, "offset": 0},
    "advertencias": [ADVERTENCIA_AGENTE_NO_VALIDADO],
    "data": [{
        "cod_cliente": 260, "cliente": "CLIENTE EJEMPLO", "grupo_deudor": "CLIENTE EJEMPLO",
        "sucursal": "Principal", "tipo_cliente": "PERSONAL", "fecha_cliente": "2015-03-10T00:00:00",
        "area": "Riesgos Generales", "ramo": "VEHICULOS DE MOTOR", "fecha_emision": "2015-03-10T00:00:00",
        "poliza": "30-95-000000", "aseguradora": "ASEGURADORA LIDER", "coaseguro": "ASEGURADORA LIDER",
        "porcentaje_participacion": "100.00", "moneda": "RD", "recibo": "4002143-4685440",
        "concepto_recibo": "PAGO DE PRIMA", "forma_pago": "TRANSFERENCIA",
        "fecha_recibo": "2026-09-30T14:31:47", "fecha_registro": "2026-09-30T14:35:02",
        "factura": "F-000000", "inicio_vig_factura": "2026-09-16T00:00:00", "dias": 14,
        "concepto": "RENOVACION", "gastos_admin": "0.0000", "prima_bruta": "29500.0000",
        "prima_neta": "25000.0000", "mantiene_porcentaje_comis": "", "recibo_comisiones": None,
        "porcentaje_comis": 15.0, "comision_generada": "3750.0000", "comision_liquidada": "0.0000",
        "diferencia": "3750.0000", "porcentaje_sobrecomis": "0.00", "sobrecomis_generada": "0.000000",
        "sobrecomis_liquidada": "0.000000", "sobrecomis_diferencia": "0.000000",
        "agente_poliza": None, "porcentaje_incentivo_agente": "0",
    }],
}


@router.get(
    "/comisiones-recibo-multivendor",
    response_model=ReporteComisionesReciboResponse,
    summary="Reporte de Comisiones Generadas Asociadas a Pólizas - Recibo Multi Vendor",
    responses={
        200: {"content": {"application/json": {"example": EJEMPLO_RESPUESTA}}},
        400: {"description": "fecha_desde es mayor que fecha_hasta"},
        500: {"description": "Error al generar el reporte (detalle solo en el log del servidor)"},
    },
)
def get_reporte_comisiones_recibo_multivendor(
    fecha_desde: date = Query(..., description="Fecha inicial (YYYY-MM-DD). Filtra por fecha del recibo o fecha de cierre de producción de la factura"),
    fecha_hasta: date = Query(..., description="Fecha final, día completo inclusive (YYYY-MM-DD)"),
    cliente: Optional[str] = Query(None, description="Filtro parcial por nombre del cliente, sin distinguir mayúsculas/minúsculas"),
    limit: Optional[int] = Query(None, ge=1, description="Máximo de filas a devolver. Omitido = todas (~2,100 filas por mes)"),
    offset: int = Query(0, ge=0, description="Filas a saltar (usar junto con limit)"),
    username: str = Depends(verify_credentials),
):
    """
    Una fila por **recibo aplicado a factura** (`imrecpol`) **por coaseguradora**
    (`imfactcoaseg`). Si la factura no tiene coaseguro declarado, sale una sola
    fila con la aseguradora líder de la póliza al 100%.

    Excluye recibos anulados (`imrecibo.lanulado = 1`). Las fechas filtran por
    `imrecibo.dfechrecibo` **o** `imfact.dfechcierreprod`, tomando días completos.

    **Campo no validado**: `agente_poliza` y `porcentaje_incentivo_agente`
    (la respuesta incluye el aviso en `advertencias`).
    """
    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=400, detail="fecha_desde no puede ser mayor que fecha_hasta.")

    cliente = cliente.strip() if cliente and cliente.strip() else None
    filtros = ReporteComisionesReciboFiltros(
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, cliente=cliente, limit=limit, offset=offset
    )

    fin_exclusivo = fecha_hasta + timedelta(days=1)
    where_extra = ""
    params = [fecha_desde, fin_exclusivo, fecha_desde, fin_exclusivo]
    if cliente:
        # imclient usa una collation sensible a mayúsculas; DATABASE_DEFAULT (CI) la hace insensible
        where_extra = " AND cli.cnomcliente COLLATE DATABASE_DEFAULT LIKE ?"
        params.append(f"%{cliente}%")

    conn = None
    try:
        conn = get_db_connection()
        conn.timeout = QUERY_TIMEOUT_SECONDS
        cursor = conn.cursor()

        cursor.execute(f"{COASEG_CTE} SELECT COUNT(*) {FROM_WHERE}{where_extra}", params)
        total = cursor.fetchone()[0]

        query = f"{COASEG_CTE} {SELECT_COLUMNS} {FROM_WHERE}{where_extra}{ORDER_BY}"
        query_params = list(params)
        if limit is not None or offset:
            query += " OFFSET ? ROWS"
            query_params.append(offset)
            if limit is not None:
                query += " FETCH NEXT ? ROWS ONLY"
                query_params.append(limit)

        cursor.execute(query, query_params)
        columns = [c[0] for c in cursor.description]
        filas = []
        for row in cursor.fetchall():
            fila = {}
            for col, value in zip(columns, row):
                if isinstance(value, str):
                    value = value.strip()
                fila[col] = value
            filas.append(fila)

        if filas:
            _aplicar_agente_poliza(cursor, filas)

        data = [
            ReporteComisionesReciboRow(**{k: v for k, v in fila.items() if not k.startswith("_")})
            for fila in filas
        ]

        return ReporteComisionesReciboResponse(
            total=total,
            filtros=filtros,
            advertencias=[ADVERTENCIA_AGENTE_NO_VALIDADO],
            data=data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error generando reporte en endpoint {ENDPOINT}",
            exc_info=True,
            extra={
                "endpoint": ENDPOINT,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query_params": filtros.model_dump(mode="json"),
                "traceback": traceback.format_exc(),
            },
        )
        # No se exponen detalles de la base de datos al cliente
        raise HTTPException(status_code=500, detail="Error al generar el reporte de comisiones por recibo.")
    finally:
        if conn:
            conn.close()
