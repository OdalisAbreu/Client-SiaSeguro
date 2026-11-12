"""
Reporte de Comisiones Generadas Asociadas a Pólizas - Recibo Multi Vendor.

Grano: una fila por recibo aplicado a factura (imrecpol), con la coaseguradora
de mayor participación de la factura (imfactcoaseg) o, si la factura no tiene
coaseguro declarado, la aseguradora líder de la póliza al 100%.

Estructura:
1. Query principal (SQL de referencia validado) con todo lo verificado.
2. analista_cobros_comisiones (impolejec '002'): se resuelve aparte, solo para
   las pólizas de la página; el OUTER APPLY solo entra al SQL principal cuando
   se filtra por `analista`.
3. agente_poliza / porcentaje_incentivo_agente: se resuelven aparte, solo para
   las pólizas de la página, en una función aislada (ver "CAMPO NO VALIDADO").
"""
from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Annotated, Optional, Iterable, List, Literal
from datetime import date, timedelta
from pydantic import BeforeValidator
from decimal import Decimal
import logging
import traceback
from models.reporte_comisiones_recibo import (
    ReporteComisionesReciboRow,
    ReporteComisionesReciboFiltros,
    ReporteComisionesReciboResponse,
    ADVERTENCIA_AGENTE_NO_VALIDADO,
    ADVERTENCIA_CAMPOS_BAJA_CONFIANZA,
)
from auth import verify_credentials
from database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

ENDPOINT = "/api/reportes/comisiones-recibo-multivendor"
QUERY_TIMEOUT_SECONDS = 120
# SQL Server admite hasta 2100 parámetros por query; se trocean las listas IN.
IN_CHUNK_SIZE = 1000

FROM_BASE = """
FROM dbo.imrecpol rp
JOIN dbo.imrecibo r            ON r.ccodrecibo     = rp.ccodrecibo
JOIN dbo.imfact f              ON f.ccodfact       = rp.ccodfact
JOIN dbo.impoliza pol          ON pol.ccodpoliza   = f.ccodpoliza
JOIN dbo.imciaseg aseg         ON aseg.ccodciaseg  = pol.ccodciaseg
JOIN dbo.imclient cli          ON cli.ccodclien    = pol.ccodclien
-- Coaseguradora, correlacionada por factura (solo se evalúa sobre las filas ya
-- filtradas): UNA sola por factura, la de mayor participación declarada en
-- imfactcoaseg o, si no hay ninguna, la aseguradora líder de la póliza al 100%.
-- Decisión del usuario: una fila por recibo aplicado a factura, no una por
-- coaseguradora (facturas con 2+ coaseguradoras salen una sola vez).
-- El TOP 1 lleva ORDER BY (nporcpart DESC, ccodciaseg) para que la elección sea
-- determinista; va en tabla derivada porque T-SQL no admite ORDER BY directo en
-- una rama de UNION ALL.
CROSS APPLY (
    SELECT x.ccodciaseg, x.nporcpart FROM (
        SELECT TOP 1 fc.ccodciaseg, fc.nporcpart
        FROM dbo.imfactcoaseg fc
        WHERE fc.ccodfact = f.ccodfact
        ORDER BY fc.nporcpart DESC, fc.ccodciaseg
    ) x
    UNION ALL
    SELECT pol.ccodciaseg, CAST(100.00 AS numeric(18,2))
    WHERE NOT EXISTS (SELECT 1 FROM dbo.imfactcoaseg fc2 WHERE fc2.ccodfact = f.ccodfact)
) cs
JOIN dbo.imciaseg caseg        ON caseg.ccodciaseg = cs.ccodciaseg
-- Prima neta aproximada del monto aplicado por el recibo (sin impuesto); se
-- calcula una vez y la usan prima_neta, comisión y sobrecomisión generadas.
CROSS APPLY (SELECT rp.yaplicado / (1 + f.bporcimp / 100.0) AS prima_neta) pn
"""

# Analista de Cobros y Comisiones (tipo de ejecutivo '002') asignado a la póliza;
# si hay varios activos, el último registrado (icodpolejec desempata).
# Solo se agrega al SQL cuando viene el filtro `analista` (para que total y
# paginación filtren bien); el valor de la columna siempre se resuelve aparte
# con _aplicar_analista_poliza, solo para las pólizas de la página.
ANALISTA_APPLY = """
OUTER APPLY (
    SELECT TOP 1 RTRIM(e.cnombres) + ' ' + RTRIM(e.capellidos) AS nombre
    FROM dbo.impolejec ie
    JOIN dbo.imejecut e ON e.ccodejecut = ie.ccodejecut
    WHERE ie.ccodpoliza = pol.ccodpoliza AND ie.ccodtipejec = '002' AND ie.tfechanulo IS NULL
    ORDER BY ie.tfechregistro DESC, ie.icodpolejec DESC
) analcc
"""

FROM_REST = """
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
  -- Solo por fecha del recibo: el OR con f.dfechcierreprod (ninguna de las dos
  -- columnas tiene índice) forzaba table scan de imrecibo e imfact.
  AND r.dfechrecibo >= ? AND r.dfechrecibo < ?
"""

# Filtros opcionales de texto parcial: (parámetro, expresión SQL).
# COLLATE DATABASE_DEFAULT (CI) porque varias columnas son *_CS_AS.
FILTROS_TEXTO = [
    ("cliente", "cli.cnomcliente"),
    ("analista", "analcc.nombre"),
    ("sucursal", "suc.cdescripcion"),
    ("area", "area.cdescripcion"),
    ("tipo_cliente", "tc.tipo"),
    ("aseguradora", "aseg.cnombre"),  # aseguradora líder de la póliza (no la coaseguradora)
]

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
    rp.yaplicado                                          AS prima_bruta,
    pn.prima_neta                                         AS prima_neta,
    (CASE WHEN pol.mantenerporcomis = 1 THEN 'Si' ELSE '' END) AS mantiene_porcentaje_comis,
    (SELECT TOP 1 ri.inumrecing FROM dbo.imrecing ri WHERE ri.ccodrecing = rp.ccodrecing)
                                                          AS recibo_comisiones,
    rp.bporcomis                                          AS porcentaje_comis,
    ROUND(pn.prima_neta * rp.bporcomis / 100.0, 2)        AS comision_generada,
    rp.ycomisrecibida                                     AS comision_liquidada,
    ROUND(pn.prima_neta * rp.bporcomis / 100.0, 2) - rp.ycomisrecibida
                                                          AS diferencia,
    rp.ysobrecomision                                     AS porcentaje_sobrecomis,
    ROUND(pn.prima_neta * rp.ysobrecomision / 100.0, 2)   AS sobrecomis_generada,
    (CASE WHEN rp.bporcomis <> 0
          THEN rp.ycomisrecibida * (rp.ysobrecomision / rp.bporcomis)
          ELSE rp.yaplicado * (pol.ysobrecomision / 100.0)
     END)                                                 AS sobrecomis_liquidada,
    (ROUND(pn.prima_neta * rp.ysobrecomision / 100.0, 2)
     - (CASE WHEN rp.bporcomis <> 0
             THEN rp.ycomisrecibida * (rp.ysobrecomision / rp.bporcomis)
             ELSE rp.yaplicado * (pol.ysobrecomision / 100.0)
        END))                                             AS sobrecomis_diferencia,
    pol.ccodpoliza                                        AS _ccodpoliza
"""

# Desempates (ccodrecpol, coaseguradora) para que la paginación sea estable
ORDER_BY = " ORDER BY cli.inumclient, r.dfechrecibo, f.cnumfact, rp.ccodrecpol, cs.ccodciaseg"


def _normalizar_moneda(value):
    # Acepta "rd"/" us " antes de validar contra el Literal; en blanco = sin filtro
    if isinstance(value, str):
        value = value.strip().upper()
        return value or None
    return value


def _normalizar_ramos(ramos: Optional[List[str]]) -> Optional[list[str]]:
    """strip a cada valor; descarta vacíos y duplicados (sin distinguir mayúsculas)."""
    vistos, resultado = set(), []
    for valor in ramos or []:
        valor = (valor or "").strip()
        if valor and valor.casefold() not in vistos:
            vistos.add(valor.casefold())
            resultado.append(valor)
    return resultado or None


def _chunks(values: list, size: int = IN_CHUNK_SIZE) -> Iterable[list]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _aplicar_analista_poliza(cursor, filas: list[dict]) -> None:
    """
    analista_cobros_comisiones por póliza, misma regla que ANALISTA_APPLY:
    ejecutivo '002' activo; si hay varios, tfechregistro DESC, icodpolejec DESC.
    """
    ccodpolizas = sorted({f["_ccodpoliza"] for f in filas if f["_ccodpoliza"]})
    por_poliza: dict[str, Optional[str]] = {}
    for chunk in _chunks(ccodpolizas):
        cursor.execute(
            f"""
            SELECT ccodpoliza, nombre FROM (
                SELECT ie.ccodpoliza,
                       RTRIM(e.cnombres) + ' ' + RTRIM(e.capellidos) AS nombre,
                       ROW_NUMBER() OVER (PARTITION BY ie.ccodpoliza
                                          ORDER BY ie.tfechregistro DESC, ie.icodpolejec DESC) AS rn
                FROM dbo.impolejec ie
                JOIN dbo.imejecut e ON e.ccodejecut = ie.ccodejecut
                WHERE ie.ccodpoliza IN ({", ".join(["?"] * len(chunk))})
                  AND ie.ccodtipejec = '002' AND ie.tfechanulo IS NULL
            ) x
            WHERE rn = 1
            """,
            chunk,
        )
        for ccodpoliza, nombre in cursor.fetchall():
            por_poliza[ccodpoliza] = nombre.strip() if isinstance(nombre, str) else nombre
    for fila in filas:
        fila["analista_cobros_comisiones"] = por_poliza.get(fila["_ccodpoliza"])


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
    "filtros": {
        "fecha_desde": "2026-09-30", "fecha_hasta": "2026-09-30", "cliente": None, "analista": None,
        "sucursal": "Principal", "area": None, "tipo_cliente": None, "aseguradora": None,
        "ramo": ["Vehículos de Motor"], "moneda": "RD", "limit": 1, "offset": 0,
    },
    "advertencias": [ADVERTENCIA_AGENTE_NO_VALIDADO, ADVERTENCIA_CAMPOS_BAJA_CONFIANZA],
    "data": [{
        "cod_cliente": 260, "cliente": "CLIENTE EJEMPLO", "grupo_deudor": "CLIENTE EJEMPLO",
        "sucursal": "Principal", "tipo_cliente": "PERSONAL", "fecha_cliente": "2015-03-10T00:00:00",
        "area": "Riesgos Generales", "ramo": "Vehículos de Motor", "fecha_emision": "2015-03-10T00:00:00",
        "poliza": "30-95-000000", "aseguradora": "ASEGURADORA LIDER", "coaseguro": "ASEGURADORA LIDER",
        "porcentaje_participacion": "100.00", "moneda": "RD", "recibo": "4002143-4685440",
        "concepto_recibo": "PAGO DE PRIMA", "forma_pago": "TRANSFERENCIA",
        "fecha_recibo": "2026-09-30T14:31:47", "fecha_registro": "2026-09-30T14:35:02",
        "factura": "F-000000", "inicio_vig_factura": "2026-09-16T00:00:00", "dias": 14,
        "concepto": "RENOVACION",
        "gastos_admin": "0.0000",                      # BAJA CONFIANZA (imfact.ygadministrativo)
        "prima_bruta": "29500.0000",                   # imrecpol.yaplicado del recibo
        "prima_neta": "25000.000000",                  # APROXIMACIÓN: yaplicado / (1 + bporcimp/100), bporcimp = 18
        "mantiene_porcentaje_comis": "", "recibo_comisiones": None,
        "porcentaje_comis": 15.0,
        "comision_generada": "3750.0000",              # ROUND(prima_neta * bporcomis / 100, 2)
        "comision_liquidada": "0.0000",                # BAJA CONFIANZA (imrecpol.ycomisrecibida)
        "diferencia": "3750.0000",                     # BAJA CONFIANZA
        "porcentaje_sobrecomis": "0.00",
        "sobrecomis_generada": "0.000000",             # ROUND(prima_neta * ysobrecomision / 100, 2)
        "sobrecomis_liquidada": "0.000000",            # BAJA CONFIANZA
        "sobrecomis_diferencia": "0.000000",           # BAJA CONFIANZA
        "agente_poliza": None, "porcentaje_incentivo_agente": "0",
        "analista_cobros_comisiones": "NOMBRE APELLIDO",
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
    fecha_desde: date = Query(..., description="Fecha inicial (YYYY-MM-DD). Filtra por la fecha del recibo (imrecibo.dfechrecibo)"),
    fecha_hasta: date = Query(..., description="Fecha final, día completo inclusive (YYYY-MM-DD)"),
    cliente: Optional[str] = Query(None, description="Filtro parcial por nombre del cliente, sin distinguir mayúsculas/minúsculas"),
    analista: Optional[str] = Query(None, description="Filtro parcial por nombre del Analista de Cobros y Comisiones de la póliza, sin distinguir mayúsculas/minúsculas"),
    sucursal: Optional[str] = Query(None, description="Filtro parcial por sucursal del cliente, sin distinguir mayúsculas/minúsculas. Ej.: Principal, Romana, Punta Cana"),
    area: Optional[str] = Query(None, description="Filtro parcial por área del ramo, sin distinguir mayúsculas/minúsculas"),
    tipo_cliente: Optional[str] = Query(None, description="Filtro parcial por tipo de cliente, sin distinguir mayúsculas/minúsculas. Ej.: PERSONAL, COMERCIAL, BANCASEGUROS, PERSONALES PREMIUM, CORPORATIVOS, GUBERNAMENTALES"),
    aseguradora: Optional[str] = Query(None, description="Filtro parcial por nombre de la aseguradora líder de la póliza, sin distinguir mayúsculas/minúsculas. Ej.: SEGUROS UNIVERSAL, HUMANO SEGUROS"),
    ramo: Optional[List[str]] = Query(None, description="Uno o varios ramos, nombre exacto sin distinguir mayúsculas/minúsculas; se repite en la URL (?ramo=Salud y Vida&ramo=Vehículos de Motor). Ej.: Salud y Vida, Vehículos de Motor, Incendio y Aliados, Fianzas, Transporte, TODO RIESGO"),
    moneda: Annotated[
        Optional[Literal["RD", "US"]],
        BeforeValidator(_normalizar_moneda),
        Query(description="Moneda de la póliza: RD = pesos, US = dólares. En blanco = ambas"),
    ] = None,
    limit: Optional[int] = Query(None, ge=1, description="Máximo de filas a devolver. Omitido = todas (~2,100 filas por mes)"),
    offset: int = Query(0, ge=0, description="Filas a saltar (usar junto con limit)"),
    username: str = Depends(verify_credentials),
):
    """
    Una fila por **recibo aplicado a factura** (`imrecpol`), con la coaseguradora
    de mayor participación de la factura (`imfactcoaseg`) o, si la factura no
    tiene coaseguro declarado, la aseguradora líder de la póliza al 100%.

    `prima_bruta` es el monto aplicado por el recibo (`imrecpol.yaplicado`);
    `prima_neta` es una aproximación: `yaplicado / (1 + imfact.bporcimp / 100)`.
    Comisión y sobrecomisión generadas se calculan sobre esa prima neta.

    Excluye recibos anulados (`imrecibo.lanulado = 1`). Las fechas filtran por
    `imrecibo.dfechrecibo`, tomando días completos.

    `analista_cobros_comisiones`: ejecutivo tipo '002' activo asignado a la
    póliza (`impolejec`); si hay varios, el último registrado.

    Filtros opcionales de texto parcial (sin distinguir mayúsculas): `cliente`,
    `analista`, `sucursal`, `area`, `tipo_cliente`, `aseguradora` (la líder de la póliza).
    `ramo`: uno o varios nombres exactos (sin distinguir mayúsculas), repitiendo
    el parámetro. `moneda`: RD o US (`impoliza.cmoneda`).

    **Campos no validados** (la respuesta incluye los avisos en `advertencias`):
    `agente_poliza` y `porcentaje_incentivo_agente`; además `gastos_admin`,
    `prima_neta` (aproximación), `comision_liquidada`, `diferencia`,
    `sobrecomis_liquidada` y `sobrecomis_diferencia`.
    """
    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=400, detail="fecha_desde no puede ser mayor que fecha_hasta.")

    textos = {
        "cliente": cliente, "analista": analista, "sucursal": sucursal,
        "area": area, "tipo_cliente": tipo_cliente, "aseguradora": aseguradora,
    }
    textos = {k: (v.strip() if v and v.strip() else None) for k, v in textos.items()}
    ramos = _normalizar_ramos(ramo)
    filtros = ReporteComisionesReciboFiltros(
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, **textos, ramo=ramos, moneda=moneda,
        limit=limit, offset=offset,
    )

    fin_exclusivo = fecha_hasta + timedelta(days=1)
    where_extra = ""
    params = [fecha_desde, fin_exclusivo]
    for nombre, columna in FILTROS_TEXTO:
        if textos[nombre]:
            # Collations *_CS_AS: DATABASE_DEFAULT (CI) hace el LIKE insensible a mayúsculas
            where_extra += f" AND {columna} COLLATE DATABASE_DEFAULT LIKE ?"
            params.append(f"%{textos[nombre]}%")
    if ramos:
        # Coincidencia exacta por nombre, insensible a mayúsculas (DATABASE_DEFAULT es CI)
        where_extra += f" AND RTRIM(ramo.cdescripcion) COLLATE DATABASE_DEFAULT IN ({', '.join(['?'] * len(ramos))})"
        params.extend(ramos)
    if moneda:
        where_extra += " AND RTRIM(pol.cmoneda) = ?"
        params.append(moneda)
    # El OUTER APPLY del analista solo hace falta para filtrar por él
    from_where = FROM_BASE + (ANALISTA_APPLY if textos["analista"] else "") + FROM_REST

    conn = None
    try:
        conn = get_db_connection()
        conn.timeout = QUERY_TIMEOUT_SECONDS
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) {from_where}{where_extra}", params)
        total = cursor.fetchone()[0]

        query = f"{SELECT_COLUMNS} {from_where}{where_extra}{ORDER_BY}"
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
            _aplicar_analista_poliza(cursor, filas)
            _aplicar_agente_poliza(cursor, filas)

        data = [
            ReporteComisionesReciboRow(**{k: v for k, v in fila.items() if not k.startswith("_")})
            for fila in filas
        ]

        return ReporteComisionesReciboResponse(
            total=total,
            filtros=filtros,
            advertencias=[ADVERTENCIA_AGENTE_NO_VALIDADO, ADVERTENCIA_CAMPOS_BAJA_CONFIANZA],
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
