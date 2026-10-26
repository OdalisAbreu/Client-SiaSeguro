"""
Reporte de Producción: una fila por factura (imfact) en un rango de fechas.

Estructura:
1. Query base (SQL validado) con los datos de factura, póliza, cliente y catálogos.
2. Campos ESTIMADO (imrecpol / t_creditos): se calculan aparte, solo para las
   facturas de la página, en funciones aisladas (ver sección "CAMPOS ESTIMADO").
3. 14 roles de personal asignado: una sola query para los clientes de la página
   y "pivot" en memoria (evita 14 subqueries correlacionadas por fila).
"""
from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional, Iterable
from datetime import date, timedelta
from decimal import Decimal
import pyodbc
import logging
import traceback
from models.reporte_produccion import (
    ReporteProduccionRow,
    ReporteProduccionFiltros,
    ReporteProduccionResponse,
    ADVERTENCIA_CAMPOS_ESTIMADOS,
)
from auth import verify_credentials
from database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

ENDPOINT = "/api/reportes/produccion"
QUERY_TIMEOUT_SECONDS = 120
# SQL Server admite hasta 2100 parámetros por query; se trocean las listas IN.
IN_CHUNK_SIZE = 1000

# Campo del JSON -> imtipejec.ccodtipejec
ROLES_EJECUTIVOS = {
    "analista_cobros_comisiones": "002",
    "analista_riesgos_personas": "006",
    "analista_riesgos_generales": "00000001",
    "analista_riesgos_internacionales": "00000003",
    "analista_rg_emision": "00000018",
    "analista_rg_movimientos": "00000019",
    "analista_rg_renovacion": "00000017",
    "asesor_reclamaciones_int": "00000004",
    "asesor_reclamaciones_rg": "00000002",
    "asesor_reclamaciones_rp": "004",
    "gestor": "003",
    "gestor_cuentas_rg": "00000005",
    "gestor_cuentas_ri": "00000009",
    "gestor_cuentas_rp": "001",
}

# Las columnas con prefijo "_" son internas: se usan para calcular otros campos
# y no se exponen en la respuesta.
BASE_FROM_WHERE = """
    FROM dbo.imfact f
    JOIN dbo.impoliza pol          ON pol.ccodpoliza = f.ccodpoliza
    JOIN dbo.imclient cli          ON cli.ccodclien  = pol.ccodclien
    LEFT JOIN dbo.imclient g       ON g.ccodclien    = cli.ccodgrupo
    LEFT JOIN dbo.imclientdet cdet ON cdet.ccodclien = cli.ccodclien
    LEFT JOIN dbo.imsucursal suc   ON suc.ccodsucursal = cdet.ccodsucursal
    LEFT JOIN dbo.imtipclient tc   ON tc.imtipclientid = cdet.imtipclientid
    JOIN dbo.imsubram sub          ON sub.ccodsubram = pol.ccodsubram
    JOIN dbo.imramos ramo          ON ramo.ccodramo  = sub.ccodramo
    LEFT JOIN dbo.imareram ar      ON ar.ccodsubram  = sub.ccodsubram
    LEFT JOIN dbo.imarea area      ON area.ccodarea  = ar.ccodarea
    JOIN dbo.imciaseg aseg         ON aseg.ccodciaseg = pol.ccodciaseg
    LEFT JOIN dbo.imfaconc conc    ON conc.ccodfaconc = f.ccodfaconc
    LEFT JOIN dbo.imfrefac frec    ON frec.ccodfrefac = pol.ccodfrefac
    -- Intervalo semiabierto: incluye todo el día fecha_hasta aunque dfechfact traiga hora
    WHERE f.dfechfact >= ? AND f.dfechfact < ?
"""

BASE_SELECT = """
    SELECT
        cli.inumclient                                      AS cod_cliente,
        RTRIM(cli.cnomcliente)                              AS cliente,
        RTRIM(ISNULL(g.cnomcliente, cli.cnomcliente))       AS grupo_deudor,
        RTRIM(suc.cdescripcion)                             AS sucursal,
        RTRIM(tc.tipo)                                      AS tipo_cliente,
        RTRIM(area.cdescripcion)                            AS area,
        RTRIM(ramo.cdescripcion)                            AS ramo,
        RTRIM(aseg.cnombre)                                 AS aseguradora,
        RTRIM(pol.cnumpoliza)                               AS poliza,
        RTRIM(pol.cmoneda)                                  AS moneda,
        f.dinivigen                                         AS inicio_vigencia,
        f.dfechcierreprod                                   AS fecha_produccion,
        RTRIM(f.cnumfact)                                   AS factura,
        RTRIM(conc.cdescripcion)                            AS concepto,
        CAST(f.dfechenviado AS DATE)                        AS fecha_remision,
        f.ysumaseg                                          AS suma_asegurada,
        pol.ytasa                                           AS tasa_facturacion,
        f.yprimaneta                                        AS prima_neta,
        f.bporcomisprod                                     AS porcentaje_comis,
        ROUND(f.yprimaneta * f.bporcomisprod / 100.0, 2)    AS comision,
        f.ysobrecomision                                    AS porcentaje_sobrecomis,
        cli.dfechingreso                                    AS fecha_ingreso_cliente,
        RTRIM(frec.cdescripcion)                            AS frecuencia_facturacion,
        pol.dfechemis                                       AS fecha_emision_poliza,
        f.ccodfact                                          AS _ccodfact,
        cli.ccodclien                                       AS _ccodclien,
        pol.ysobrecomision                                  AS _pol_ysobrecomision
"""


def _chunks(values: list, size: int = IN_CHUNK_SIZE) -> Iterable[list]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _placeholders(n: int) -> str:
    return ", ".join(["?"] * n)


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    # float -> str -> Decimal para no arrastrar error binario
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# CAMPOS ESTIMADO
# TODO(reporte-produccion): las fórmulas de esta sección NO están validadas
# contra el reporte original. Ajustarlas aquí cuando el equipo de cobros
# confirme los montos; el resto del endpoint no depende de cómo se calculan.
# ---------------------------------------------------------------------------

def _estimado_cobros_por_factura(cursor, ccodfacts: list[str]) -> dict[str, tuple[Decimal, Decimal]]:
    """
    ESTIMADO. ccodfact -> (prima_neta_cobrada, comision_liquidada).
    prima_neta_cobrada = SUM(imrecpol.yaplicado)
    comision_liquidada = SUM(imrecpol.ycomisrecibida)  (suele dar 0, el más incierto)
    """
    resultado: dict[str, tuple[Decimal, Decimal]] = {}
    for chunk in _chunks(ccodfacts):
        cursor.execute(
            f"""
            SELECT ccodfact, SUM(yaplicado), SUM(ycomisrecibida)
            FROM dbo.imrecpol
            WHERE ccodfact IN ({_placeholders(len(chunk))})
            GROUP BY ccodfact
            """,
            chunk,
        )
        for ccodfact, aplicado, comis in cursor.fetchall():
            resultado[ccodfact] = (aplicado or Decimal("0"), comis or Decimal("0"))
    return resultado


def _estimado_creditos_por_factura(cursor, facturas: list[str]) -> dict[tuple[str, str], Decimal]:
    """
    ESTIMADO. (poliza, factura) normalizados -> SUM(t_creditos.montooper) con anulado = 0.
    t_creditos usa Latin1_General_CI_AS y imfact/impoliza SQL_Latin1_General_CP1_CS_AS:
    se aplica COLLATE DATABASE_DEFAULT para evitar el conflicto de collation.
    """
    resultado: dict[tuple[str, str], Decimal] = {}
    for chunk in _chunks(facturas):
        cursor.execute(
            f"""
            SELECT numpoliza, numfactura, SUM(montooper)
            FROM dbo.t_creditos
            WHERE anulado = 0
              AND numfactura COLLATE DATABASE_DEFAULT IN ({_placeholders(len(chunk))})
            GROUP BY numpoliza, numfactura
            """,
            chunk,
        )
        for numpoliza, numfactura, monto in cursor.fetchall():
            clave = ((numpoliza or "").strip().upper(), (numfactura or "").strip().upper())
            resultado[clave] = resultado.get(clave, Decimal("0")) + (monto or Decimal("0"))
    return resultado


def _estimado_sobrecomis_liquidada(
    porcentaje_comis,
    porcentaje_sobrecomis,
    pol_ysobrecomision,
    comision_liquidada: Optional[Decimal],
    prima_neta_cobrada: Optional[Decimal],
) -> Optional[Decimal]:
    """
    ESTIMADO.
    - bporcomisprod != 0: comision_liquidada * (imfact.ysobrecomision / imfact.bporcomisprod)
    - bporcomisprod == 0: prima_neta_cobrada * (impoliza.ysobrecomision / 100)
    """
    porc_comis = _to_decimal(porcentaje_comis) or Decimal("0")
    if porc_comis != 0:
        sobre = _to_decimal(porcentaje_sobrecomis)
        if sobre is None or comision_liquidada is None:
            return None
        return comision_liquidada * (sobre / porc_comis)
    sobre_pol = _to_decimal(pol_ysobrecomision)
    if sobre_pol is None or prima_neta_cobrada is None:
        return None
    return prima_neta_cobrada * (sobre_pol / Decimal("100"))


def _aplicar_campos_estimados(cursor, filas: list[dict]) -> None:
    ccodfacts = sorted({f["_ccodfact"] for f in filas if f["_ccodfact"]})
    facturas = sorted({f["factura"] for f in filas if f["factura"]})
    cobros = _estimado_cobros_por_factura(cursor, ccodfacts)
    creditos = _estimado_creditos_por_factura(cursor, facturas)

    for fila in filas:
        cobrada, comis_liq = cobros.get(fila["_ccodfact"], (Decimal("0"), Decimal("0")))
        clave = ((fila["poliza"] or "").upper(), (fila["factura"] or "").upper())
        fila["prima_neta_cobrada"] = cobrada
        fila["comision_liquidada"] = comis_liq
        fila["creditos_aplicados"] = creditos.get(clave, Decimal("0"))
        fila["sobrecomis_liquidada"] = _estimado_sobrecomis_liquidada(
            fila["porcentaje_comis"],
            fila["porcentaje_sobrecomis"],
            fila["_pol_ysobrecomision"],
            comis_liq,
            cobrada,
        )

# ------------------------- fin CAMPOS ESTIMADO -----------------------------


def _aplicar_roles_ejecutivos(cursor, filas: list[dict]) -> None:
    """
    Trae en una sola pasada los ejecutivos activos (tfechanulo IS NULL) de los
    clientes de la página y hace el pivot en memoria.

    En la base hay pares cliente+rol con más de un ejecutivo activo; se toma el
    de registro más reciente (tfechregistro, y luego icodcliejec) para que el
    resultado sea determinista.
    """
    clientes = sorted({f["_ccodclien"] for f in filas if f["_ccodclien"]})
    codigos = list(ROLES_EJECUTIVOS.values())
    asignados: dict[tuple[str, str], str] = {}

    # Deja espacio para los parámetros de los códigos de rol dentro del límite de 2100
    for chunk in _chunks(clientes, IN_CHUNK_SIZE):
        cursor.execute(
            f"""
            SELECT ce.ccodclien, RTRIM(ce.ccodtipejec),
                   LTRIM(RTRIM(ISNULL(RTRIM(e.cnombres), '') + ' ' + ISNULL(RTRIM(e.capellidos), '')))
            FROM dbo.imcliejec ce
            JOIN dbo.imejecut e ON e.ccodejecut = ce.ccodejecut
            WHERE ce.tfechanulo IS NULL
              AND ce.ccodclien IN ({_placeholders(len(chunk))})
              AND ce.ccodtipejec IN ({_placeholders(len(codigos))})
            ORDER BY ce.ccodclien, ce.ccodtipejec, ce.tfechregistro DESC, ce.icodcliejec DESC
            """,
            chunk + codigos,
        )
        for ccodclien, ccodtipejec, nombre in cursor.fetchall():
            # Por el ORDER BY, el primero de cada par es el más reciente
            asignados.setdefault((ccodclien, ccodtipejec), nombre or None)

    for fila in filas:
        for campo, codigo in ROLES_EJECUTIVOS.items():
            fila[campo] = asignados.get((fila["_ccodclien"], codigo))


EJEMPLO_RESPUESTA = {
    "total": 906,
    "filtros": {"fecha_desde": "2026-08-01", "fecha_hasta": "2026-08-31", "limit": 1, "offset": 0},
    "advertencias": [ADVERTENCIA_CAMPOS_ESTIMADOS],
    "data": [{
        "cod_cliente": 260, "cliente": "CLIENTE EJEMPLO", "grupo_deudor": "CLIENTE EJEMPLO",
        "sucursal": "Principal", "tipo_cliente": "PERSONAL", "area": "Riesgos Generales",
        "ramo": "VEHICULOS DE MOTOR", "aseguradora": "ASEGURADORA EJEMPLO",
        "poliza": "30-95-000000", "moneda": "RD", "inicio_vigencia": "2026-08-01T00:00:00",
        "fecha_produccion": None, "factura": "F-000000", "concepto": "RENOVACION",
        "fecha_remision": "2026-08-05", "suma_asegurada": "1500000.0000",
        "tasa_facturacion": "0.0000", "prima_neta": "25000.0000", "porcentaje_comis": 15.0,
        "comision": "3750.0000", "prima_neta_cobrada": "25000.0000", "creditos_aplicados": "0",
        "comision_liquidada": "0.0000", "porcentaje_sobrecomis": "0.00",
        "sobrecomis_liquidada": "0.000000", "fecha_ingreso_cliente": "2015-03-10T00:00:00",
        "frecuencia_facturacion": "ANUAL", "fecha_emision_poliza": "2015-03-10T00:00:00",
        "analista_cobros_comisiones": "NOMBRE APELLIDO", "gestor": "NOMBRE APELLIDO",
        "analista_riesgos_personas": None,
    }],
}


@router.get(
    "/produccion",
    response_model=ReporteProduccionResponse,
    summary="Reporte de Producción (facturas por rango de fechas)",
    responses={
        200: {"content": {"application/json": {"example": EJEMPLO_RESPUESTA}}},
        400: {"description": "fecha_desde es mayor que fecha_hasta"},
        500: {"description": "Error al generar el reporte (detalle solo en el log del servidor)"},
    },
)
def get_reporte_produccion(
    fecha_desde: date = Query(..., description="Fecha inicial de factura (imfact.dfechfact), formato YYYY-MM-DD"),
    fecha_hasta: date = Query(..., description="Fecha final de factura, inclusive, formato YYYY-MM-DD"),
    limit: Optional[int] = Query(
        None, ge=1,
        description="Máximo de filas a devolver. Omitido = todas (el reporte original no pagina; ~900 facturas por mes)"
    ),
    offset: int = Query(0, ge=0, description="Filas a saltar (usar junto con limit)"),
    username: str = Depends(verify_credentials),
):
    """
    Reporte de Producción: **una fila por factura** (`imfact`) con `dfechfact`
    entre `fecha_desde` y `fecha_hasta` (ambas inclusive), con datos del cliente,
    póliza, aseguradora, montos y los 14 roles de personal asignado al cliente.

    Orden: código de cliente, fecha de factura.

    **Campos ESTIMADO** (pendientes de validar contra el reporte original):
    `prima_neta_cobrada`, `creditos_aplicados`, `comision_liquidada` y
    `sobrecomis_liquidada`. La respuesta incluye un aviso en `advertencias`.
    """
    if fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=400,
            detail="fecha_desde no puede ser mayor que fecha_hasta.",
        )

    filtros = ReporteProduccionFiltros(
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, limit=limit, offset=offset
    )
    params_fecha = [fecha_desde, fecha_hasta + timedelta(days=1)]

    conn = None
    try:
        conn = get_db_connection()
        conn.timeout = QUERY_TIMEOUT_SECONDS
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) {BASE_FROM_WHERE}", params_fecha)
        total = cursor.fetchone()[0]

        # f.ccodfact como desempate para que la paginación sea estable
        query = f"{BASE_SELECT} {BASE_FROM_WHERE} ORDER BY cli.inumclient, f.dfechfact, f.ccodfact"
        params = list(params_fecha)
        if limit is not None or offset:
            query += " OFFSET ? ROWS"
            params.append(offset)
            if limit is not None:
                query += " FETCH NEXT ? ROWS ONLY"
                params.append(limit)

        cursor.execute(query, params)
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
            _aplicar_campos_estimados(cursor, filas)
            _aplicar_roles_ejecutivos(cursor, filas)

        data = [
            ReporteProduccionRow(**{k: v for k, v in fila.items() if not k.startswith("_")})
            for fila in filas
        ]

        return ReporteProduccionResponse(
            total=total,
            filtros=filtros,
            advertencias=[ADVERTENCIA_CAMPOS_ESTIMADOS],
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
        raise HTTPException(status_code=500, detail="Error al generar el reporte de producción.")
    finally:
        if conn:
            conn.close()
