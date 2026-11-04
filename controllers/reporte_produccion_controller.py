"""
Reporte de Producción: una fila por factura (imfact) en un rango de fechas.

Estructura:
1. Query base (SQL validado) con los datos de factura, póliza, cliente y catálogos.
2. Campos de cobros (imrecpol + imrecibo): una sola query para las facturas de
   la página y cálculo en memoria (ver sección "CAMPOS DE COBROS POR RECIBO").
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
# CAMPOS DE COBROS POR RECIBO
# prima_neta_cobrada, comision_liquidada, sobrecomis_liquidada, creditos_aplicados
# y porcentaje_comis_recibo salen de las aplicaciones de recibos a la factura
# (imrecpol), excluyendo recibos anulados (imrecibo.lanulado = 1).
#
# TODO: revalidar cuando llegue el backup actualizado de la BD.
# Con la copia actual cuadran exacto las facturas "limpias" (un recibo, pagadas
# completas), pero no las de cuotas/endosos múltiples (facturas de referencia
# del caso abierto: 003672555 y 10495501). Se atribuye a que el backup no está
# sincronizado con los datos que generaron el Excel original.
# ---------------------------------------------------------------------------

TIPO_RECIBO_NOTA_CREDITO = "NOTCRED"


def _recibos_por_factura(cursor, ccodfacts: list[str]) -> dict[str, list[dict]]:
    """
    Una sola pasada por imrecpol + imrecibo para todas las facturas de la página:
    ccodfact -> lista de aplicaciones de recibos no anulados.
    """
    resultado: dict[str, list[dict]] = {}
    for chunk in _chunks(ccodfacts):
        cursor.execute(
            f"""
            SELECT rp.ccodfact, rp.yaplicado, rp.ycomisrecibida, rp.bporcomis,
                   rp.ysobrecomision, RTRIM(rp.ccodtiprecpol), r.dfechrecibo, r.ccodrecibo
            FROM dbo.imrecpol rp
            JOIN dbo.imrecibo r ON r.ccodrecibo = rp.ccodrecibo
            WHERE r.lanulado = 0
              AND rp.ccodfact IN ({_placeholders(len(chunk))})
            """,
            chunk,
        )
        for ccodfact, aplicado, comis, porcomis, sobrecomis, tipo, fecha, ccodrecibo in cursor.fetchall():
            resultado.setdefault(ccodfact, []).append({
                "aplicado": _to_decimal(aplicado) or Decimal("0"),
                "comis_recibida": _to_decimal(comis) or Decimal("0"),
                "porcomis": _to_decimal(porcomis) or Decimal("0"),
                "sobrecomis": _to_decimal(sobrecomis) or Decimal("0"),
                "tipo": (tipo or "").strip().upper(),
                "fecha": fecha,
                "ccodrecibo": ccodrecibo or "",
            })
    return resultado


def _sobrecomis_recibo(recibo: dict, pol_ysobrecomision: Decimal) -> Decimal:
    """
    Fórmula de dos ramas, por recibo (el %comis y el %sobrecomis pueden variar
    entre recibos de una misma factura si hubo cambio de tasa):
    - imrecpol.bporcomis != 0: ycomisrecibida * (imrecpol.ysobrecomision / imrecpol.bporcomis)
    - imrecpol.bporcomis == 0: yaplicado * (impoliza.ysobrecomision / 100)
    """
    if recibo["porcomis"] != 0:
        return recibo["comis_recibida"] * (recibo["sobrecomis"] / recibo["porcomis"])
    return recibo["aplicado"] * (pol_ysobrecomision / Decimal("100"))


def _recibo_mas_reciente(recibos: list[dict]) -> Optional[dict]:
    """dfechrecibo DESC; ccodrecibo desempata recibos del mismo instante."""
    con_fecha = [r for r in recibos if r["fecha"] is not None]
    if not con_fecha:
        return None
    return max(con_fecha, key=lambda r: (r["fecha"], r["ccodrecibo"]))


def _calcular_cobros(recibos: list[dict], pol_ysobrecomision) -> dict:
    sobre_pol = _to_decimal(pol_ysobrecomision) or Decimal("0")
    reciente = _recibo_mas_reciente(recibos)
    return {
        "prima_neta_cobrada": sum((r["aplicado"] for r in recibos), Decimal("0")),
        "comision_liquidada": sum((r["comis_recibida"] for r in recibos), Decimal("0")),
        "sobrecomis_liquidada": sum((_sobrecomis_recibo(r, sobre_pol) for r in recibos), Decimal("0")),
        "creditos_aplicados": sum(
            (r["aplicado"] for r in recibos if r["tipo"] == TIPO_RECIBO_NOTA_CREDITO), Decimal("0")
        ),
        "porcentaje_comis_recibo": float(reciente["porcomis"]) if reciente else None,
    }


def _aplicar_campos_cobros(cursor, filas: list[dict]) -> None:
    ccodfacts = sorted({f["_ccodfact"] for f in filas if f["_ccodfact"]})
    recibos = _recibos_por_factura(cursor, ccodfacts)

    for fila in filas:
        fila.update(_calcular_cobros(recibos.get(fila["_ccodfact"], []), fila["_pol_ysobrecomision"]))

# --------------------- fin CAMPOS DE COBROS POR RECIBO ---------------------


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
        "comision": "3750.0000", "porcentaje_comis_recibo": 15.0, "prima_neta_cobrada": "25000.0000", "creditos_aplicados": "0",
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

    **Campos de cobros por recibo** (`imrecpol` + `imrecibo`, sin recibos anulados):
    `prima_neta_cobrada`, `creditos_aplicados` (solo recibos `NOTCRED`),
    `comision_liquidada`, `sobrecomis_liquidada` y `porcentaje_comis_recibo`
    (del recibo más reciente). Pendientes de revalidar contra el reporte original
    con un backup actualizado de la BD; la respuesta incluye un aviso en `advertencias`.
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
            _aplicar_campos_cobros(cursor, filas)
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
