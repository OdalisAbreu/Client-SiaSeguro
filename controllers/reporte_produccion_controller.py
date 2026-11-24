"""
Reporte de Producción ("Reporte de produccion - Lineal" del sistema).

Filas = facturas + notas de crédito + notas de débito, por inicio de vigencia:
- FACTURA:       dbo.imfact, una fila por factura.
- NOTA_CREDITO:  dbo.imrecibo.ccodrectipo = '00000003', prima en negativo.
- NOTA_DEBITO:   dbo.imrecibo.ccodrectipo = '00000005', prima en positivo.
  Las notas dan una fila por (recibo, factura a la que se aplican).

Estructura:
1. Query base con los documentos de la página, póliza, cliente y catálogos.
2. Cobros, créditos y liquidación de comisiones de las facturas de la página:
   una query por tabla y cálculo en memoria (ver "CAMPOS DE COBROS").
3. 14 roles de personal asignado a la póliza: una query y pivot en memoria.

Validado columna por columna contra el Excel real de octubre 2026 (moneda RD,
822 filas): 820 filas coinciden en factura + póliza + prima neta. Las
diferencias que quedan son cobros, comisiones y reasignaciones que el Excel
trae y el backup usado para validar todavía no.
"""
from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional, Iterable
from datetime import date, timedelta
from decimal import Decimal
import logging
import traceback
from models.reporte_produccion import (
    ReporteProduccionRow,
    ReporteProduccionFiltros,
    ReporteProduccionResponse,
)
from auth import verify_credentials
from database import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

ENDPOINT = "/api/reportes/produccion"
QUERY_TIMEOUT_SECONDS = 120
# SQL Server admite hasta 2100 parámetros por query; se trocean las listas IN.
IN_CHUNK_SIZE = 1000

RECTIPO_NOTA_CREDITO = "00000003"
RECTIPO_NOTA_DEBITO = "00000005"
TIPO_INGRESO_COMISION = 1
TIPO_INGRESO_SOBRECOMISION = 2

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

# Documentos del reporte. Lleva 4 marcadores de fecha: desde/hasta de las
# facturas y desde/hasta de las notas (intervalo semiabierto, incluye todo el
# dia fecha_hasta). Las notas sin inicio de vigencia usan la fecha del recibo.
# La prima de las notas es lo aplicado, sin impuesto y con el signo del tipo.
DOCS_CTE = f"""
    WITH docs AS (
        SELECT
            CAST('FACTURA' AS varchar(20))                      AS tipo_doc,
            CAST(f.ccodfact AS varchar(40))                     AS clave,
            f.ccodfact                                          AS ccodfact_cobros,
            f.ccodpoliza                                        AS ccodpoliza,
            RTRIM(pol.cmoneda) COLLATE DATABASE_DEFAULT         AS moneda,
            f.dinivigen                                         AS inicio_vigencia,
            f.dfechcierreprod                                   AS fecha_produccion,
            LTRIM(RTRIM(f.cnumfact)) COLLATE DATABASE_DEFAULT   AS factura,
            f.ccodfaconc COLLATE DATABASE_DEFAULT               AS ccodfaconc,
            f.dfechenviado                                      AS fecha_enviado,
            CAST(f.ysumaseg AS decimal(19,4))                   AS suma_asegurada,
            CAST(f.yprimaneta AS decimal(19,4))                 AS prima_neta,
            CAST(f.bporcomisprod AS float)                      AS pct_comis,
            CAST(f.ysobrecomision AS decimal(18,2))             AS pct_sobrecomis,
            CAST(ISNULL(f.bporcimp, 0) AS float)                AS pct_impuesto
        FROM dbo.imfact f
        JOIN dbo.impoliza pol ON pol.ccodpoliza = f.ccodpoliza
        WHERE f.dinivigen >= ? AND f.dinivigen < ?

        UNION ALL

        SELECT
            CAST(CASE r.ccodrectipo WHEN '{RECTIPO_NOTA_CREDITO}' THEN 'NOTA_CREDITO' ELSE 'NOTA_DEBITO' END AS varchar(20)),
            CAST(r.ccodrecibo + '-' + rp.ccodfact AS varchar(40)),
            CAST(NULL AS char(8)),
            f.ccodpoliza,
            RTRIM(r.cmoneda) COLLATE DATABASE_DEFAULT,
            COALESCE(r.dinivigen, r.dfechrecibo),
            r.dfechcierreprod,
            LTRIM(RTRIM(r.cnumrecprov)) COLLATE DATABASE_DEFAULT,
            r.ccodfaconc COLLATE DATABASE_DEFAULT,
            r.dfechenviado,
            CAST(MAX(pn.ycantaseg) AS decimal(19,4)),
            CAST((CASE r.ccodrectipo WHEN '{RECTIPO_NOTA_CREDITO}' THEN -1 ELSE 1 END)
                 * SUM(rp.yaplicado) / (1 + ISNULL(MAX(f.bporcimp), 0) / 100.0) AS decimal(19,4)),
            CAST(MAX(rp.bporcomis) AS float),
            CAST(MAX(rp.ysobrecomision) AS decimal(18,2)),
            CAST(ISNULL(MAX(f.bporcimp), 0) AS float)
        FROM dbo.imrecibo r
        JOIN dbo.imrecpol rp ON rp.ccodrecibo = r.ccodrecibo
        JOIN dbo.imfact f    ON f.ccodfact    = rp.ccodfact
        JOIN dbo.impoliza pn ON pn.ccodpoliza = f.ccodpoliza
        WHERE r.ccodrectipo IN ('{RECTIPO_NOTA_CREDITO}', '{RECTIPO_NOTA_DEBITO}')
          AND r.lanulado = 0
          AND COALESCE(r.dinivigen, r.dfechrecibo) >= ?
          AND COALESCE(r.dinivigen, r.dfechrecibo) <  ?
        GROUP BY r.ccodrecibo, r.ccodrectipo, r.cmoneda, r.dinivigen, r.dfechrecibo, r.dfechcierreprod,
                 r.cnumrecprov, r.ccodfaconc, r.dfechenviado, rp.ccodfact, f.ccodpoliza
    )
"""

# El conteo usa los mismos JOIN obligatorios que el SELECT para que "total"
# coincida con las filas devueltas.
BASE_FROM = """
    FROM docs d
    JOIN dbo.impoliza pol          ON pol.ccodpoliza   = d.ccodpoliza
    JOIN dbo.imclient cli          ON cli.ccodclien    = pol.ccodclien
    LEFT JOIN dbo.imclient g       ON g.ccodclien      = cli.ccodgrupo
    LEFT JOIN dbo.imclientdet cdet ON cdet.ccodclien   = cli.ccodclien
    LEFT JOIN dbo.imsucursal suc   ON suc.ccodsucursal = cdet.ccodsucursal
    LEFT JOIN dbo.imtipclient tc   ON tc.imtipclientid = cdet.imtipclientid
    JOIN dbo.imsubram sub          ON sub.ccodsubram   = pol.ccodsubram
    LEFT JOIN dbo.imareram ar      ON ar.ccodsubram    = sub.ccodsubram
    LEFT JOIN dbo.imarea area      ON area.ccodarea    = ar.ccodarea
    JOIN dbo.imciaseg aseg         ON aseg.ccodciaseg  = pol.ccodciaseg
    LEFT JOIN dbo.imfaconc conc    ON conc.ccodfaconc  = d.ccodfaconc
    LEFT JOIN dbo.imfrefac frec    ON frec.ccodfrefac  = pol.ccodfrefac
"""

# Las columnas con prefijo "_" son internas: se usan para calcular otros campos
# y no se exponen en la respuesta.
# - Las personas (icompania = 2) llevan apellidos; las compañías no.
# - "ramo" es el sub-ramo (imsubram) y "aseguradora" las siglas, como en el reporte.
# - La comisión se calcula en punto flotante y multiplicando por (% / 100),
#   igual que el reporte original, para redondear igual los medios centavos.
BASE_SELECT = """
    SELECT
        d.tipo_doc                                          AS tipo_documento,
        cli.inumclient                                      AS cod_cliente,
        RTRIM(cli.cnomcliente)
            + CASE WHEN cli.icompania = 2 AND RTRIM(ISNULL(cli.capellidos, '')) <> ''
                   THEN ' ' + RTRIM(cli.capellidos) ELSE '' END
                                                            AS cliente,
        CASE WHEN g.ccodclien IS NULL
             THEN RTRIM(cli.cnomcliente)
                  + CASE WHEN cli.icompania = 2 AND RTRIM(ISNULL(cli.capellidos, '')) <> ''
                         THEN ' ' + RTRIM(cli.capellidos) ELSE '' END
             ELSE RTRIM(g.cnomcliente)
                  + CASE WHEN g.icompania = 2 AND RTRIM(ISNULL(g.capellidos, '')) <> ''
                         THEN ' ' + RTRIM(g.capellidos) ELSE '' END
        END                                                 AS grupo_deudor,
        RTRIM(suc.cdescripcion)                             AS sucursal,
        RTRIM(tc.tipo)                                      AS tipo_cliente,
        RTRIM(area.cdescripcion)                            AS area,
        RTRIM(sub.cdescripcion)                             AS ramo,
        RTRIM(aseg.csiglas)                                 AS aseguradora,
        RTRIM(pol.cnumpoliza)                               AS poliza,
        d.moneda                                            AS moneda,
        d.inicio_vigencia                                   AS inicio_vigencia,
        d.fecha_produccion                                  AS fecha_produccion,
        d.factura                                           AS factura,
        RTRIM(conc.cdescripcion)                            AS concepto,
        CAST(d.fecha_enviado AS DATE)                       AS fecha_remision,
        d.suma_asegurada                                    AS suma_asegurada,
        pol.ytasa                                           AS tasa_facturacion,
        d.prima_neta                                        AS prima_neta,
        d.pct_comis                                         AS porcentaje_comis,
        ROUND(CAST(d.prima_neta AS float) * (d.pct_comis / 100e0), 2) AS comision,
        d.pct_sobrecomis                                    AS porcentaje_sobrecomis,
        cli.fechaCreacionCliente                            AS fecha_ingreso_cliente,
        RTRIM(frec.cdescripcion)                            AS frecuencia_facturacion,
        pol.dfechemis                                       AS fecha_emision_poliza,
        d.ccodfact_cobros                                   AS _ccodfact,
        d.ccodpoliza                                        AS _ccodpoliza,
        d.pct_impuesto                                      AS _pct_impuesto
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


CENTESIMA_DE_CENTAVO = Decimal("0.0001")
CERO = Decimal("0")


# ---------------------------------------------------------------------------
# CAMPOS DE COBROS (solo filas FACTURA; en las notas van en 0)
#
# - prima_neta_cobrada: lo aplicado a la factura por recibos no anulados que
#   NO son nota de crédito, sin impuesto (yaplicado / (1 + bporcimp/100)).
# - creditos_aplicados: lo aplicado desde notas de crédito, sin impuesto.
# - comision_liquidada / sobrecomis_liquidada: lo recibido en los recibos de
#   ingreso de comisión (imrecingdet.comisionrecibida) sin las líneas
#   rechazadas (estatus 'R'). imTipoIngresoId 1 = comisión, 2 = sobrecomisión.
#   imrecpol.ycomisrecibida NO sirve: viene siempre en 0.
# - porcentaje_comis_recibo: % comis del recibo más reciente de la factura.
# ---------------------------------------------------------------------------

def _recibos_por_factura(cursor, ccodfacts: list[str]) -> dict[str, list[dict]]:
    """ccodfact -> aplicaciones de recibos no anulados."""
    resultado: dict[str, list[dict]] = {}
    for chunk in _chunks(ccodfacts):
        cursor.execute(
            f"""
            SELECT rp.ccodfact, rp.yaplicado, rp.bporcomis, RTRIM(r.ccodrectipo), r.dfechrecibo, r.ccodrecibo
            FROM dbo.imrecpol rp
            JOIN dbo.imrecibo r ON r.ccodrecibo = rp.ccodrecibo
            WHERE r.lanulado = 0
              AND rp.ccodfact IN ({_placeholders(len(chunk))})
            """,
            chunk,
        )
        for ccodfact, aplicado, porcomis, rectipo, fecha, ccodrecibo in cursor.fetchall():
            resultado.setdefault(ccodfact, []).append({
                "aplicado": _to_decimal(aplicado) or CERO,
                "porcomis": porcomis,
                "es_nota_credito": (rectipo or "").strip() == RECTIPO_NOTA_CREDITO,
                "fecha": fecha,
                "ccodrecibo": ccodrecibo or "",
            })
    return resultado


def _liquidado_por_factura(cursor, ccodfacts: list[str]) -> dict[tuple[str, int], Decimal]:
    """(ccodfact, imTipoIngresoId) -> comisión recibida, sin líneas rechazadas."""
    resultado: dict[tuple[str, int], Decimal] = {}
    for chunk in _chunks(ccodfacts):
        cursor.execute(
            f"""
            SELECT RTRIM(d.ccodfact), d.imTipoIngresoId, SUM(d.comisionrecibida)
            FROM dbo.imrecingdet d
            WHERE ISNULL(d.estatus, '') <> 'R'
              AND d.ccodfact IN ({_placeholders(len(chunk))})
            GROUP BY RTRIM(d.ccodfact), d.imTipoIngresoId
            """,
            chunk,
        )
        for ccodfact, tipo_ingreso, recibida in cursor.fetchall():
            resultado[(ccodfact, tipo_ingreso)] = _to_decimal(recibida) or CERO
    return resultado


def _recibo_mas_reciente(recibos: list[dict]) -> Optional[dict]:
    """dfechrecibo DESC; ccodrecibo desempata recibos del mismo instante."""
    con_fecha = [r for r in recibos if r["fecha"] is not None]
    if not con_fecha:
        return None
    return max(con_fecha, key=lambda r: (r["fecha"], r["ccodrecibo"]))


def _sin_impuesto(monto: Decimal, pct_impuesto) -> Decimal:
    divisor = Decimal("1") + (_to_decimal(pct_impuesto) or CERO) / Decimal("100")
    return (monto / divisor).quantize(CENTESIMA_DE_CENTAVO)


def _aplicar_campos_cobros(cursor, filas: list[dict]) -> None:
    ccodfacts = sorted({f["_ccodfact"] for f in filas if f["_ccodfact"]})
    recibos = _recibos_por_factura(cursor, ccodfacts)
    liquidado = _liquidado_por_factura(cursor, ccodfacts)

    for fila in filas:
        ccodfact = fila["_ccodfact"]
        de_la_factura = recibos.get(ccodfact, []) if ccodfact else []
        reciente = _recibo_mas_reciente(de_la_factura)
        cobrado = sum((r["aplicado"] for r in de_la_factura if not r["es_nota_credito"]), CERO)
        creditos = sum((r["aplicado"] for r in de_la_factura if r["es_nota_credito"]), CERO)
        fila["prima_neta_cobrada"] = _sin_impuesto(cobrado, fila["_pct_impuesto"])
        fila["creditos_aplicados"] = _sin_impuesto(creditos, fila["_pct_impuesto"])
        fila["comision_liquidada"] = liquidado.get((ccodfact, TIPO_INGRESO_COMISION), CERO)
        fila["sobrecomis_liquidada"] = liquidado.get((ccodfact, TIPO_INGRESO_SOBRECOMISION), CERO)
        fila["porcentaje_comis_recibo"] = (
            float(reciente["porcomis"]) if reciente and reciente["porcomis"] is not None else None
        )

# --------------------------- fin CAMPOS DE COBROS ---------------------------


def _aplicar_roles_ejecutivos(cursor, filas: list[dict]) -> None:
    """
    Personal asignado a la PÓLIZA (impolejec), no al cliente: una sola pasada
    por las pólizas de la página y pivot en memoria.

    Cuando una póliza tiene más de un ejecutivo vigente (tfechanulo IS NULL)
    para el mismo rol, el reporte original muestra el de registro más antiguo.
    """
    polizas = sorted({f["_ccodpoliza"] for f in filas if f["_ccodpoliza"]})
    codigos = list(ROLES_EJECUTIVOS.values())
    asignados: dict[tuple[str, str], str] = {}

    # Deja espacio para los parámetros de los códigos de rol dentro del límite de 2100
    for chunk in _chunks(polizas, IN_CHUNK_SIZE):
        cursor.execute(
            f"""
            SELECT pe.ccodpoliza, RTRIM(pe.ccodtipejec),
                   LTRIM(RTRIM(ISNULL(RTRIM(e.cnombres), '') + ' ' + ISNULL(RTRIM(e.capellidos), '')))
            FROM dbo.impolejec pe
            JOIN dbo.imejecut e ON e.ccodejecut = pe.ccodejecut
            WHERE pe.tfechanulo IS NULL
              AND pe.ccodpoliza IN ({_placeholders(len(chunk))})
              AND pe.ccodtipejec IN ({_placeholders(len(codigos))})
            ORDER BY pe.ccodpoliza, pe.ccodtipejec, pe.tfechregistro ASC, pe.icodpolejec ASC
            """,
            chunk + codigos,
        )
        for ccodpoliza, ccodtipejec, nombre in cursor.fetchall():
            # Por el ORDER BY, el primero de cada par es el de registro más antiguo
            asignados.setdefault((ccodpoliza, ccodtipejec), nombre or None)

    for fila in filas:
        for campo, codigo in ROLES_EJECUTIVOS.items():
            fila[campo] = asignados.get((fila["_ccodpoliza"], codigo))


EJEMPLO_RESPUESTA = {
    "total": 826,
    "filtros": {"fecha_desde": "2026-10-01", "fecha_hasta": "2026-10-31", "moneda": "RD", "limit": 1, "offset": 0},
    "advertencias": [],
    "data": [{
        "tipo_documento": "FACTURA",
        "cod_cliente": 260, "cliente": "NOMBRE APELLIDO", "grupo_deudor": "NOMBRE APELLIDO",
        "sucursal": "Principal", "tipo_cliente": "PERSONAL", "area": "Riesgos Generales",
        "ramo": "VEHICULOS", "aseguradora": "ASEGURADORA",
        "poliza": "AUTO-000000", "moneda": "RD", "inicio_vigencia": "2026-10-01T00:00:00",
        "fecha_produccion": None, "factura": "000000000", "concepto": "Renovación",
        "fecha_remision": "2026-09-25", "suma_asegurada": "1500000.0000",
        "tasa_facturacion": "0.0200", "prima_neta": "25000.0000", "porcentaje_comis": 17.5,
        "comision": "4375.0", "porcentaje_comis_recibo": 17.5, "prima_neta_cobrada": "25000.0000",
        "creditos_aplicados": "0.0000", "comision_liquidada": "4375.00", "porcentaje_sobrecomis": "2.50",
        "sobrecomis_liquidada": "625.00", "fecha_ingreso_cliente": "2015-03-10T09:30:00",
        "frecuencia_facturacion": "Anual", "fecha_emision_poliza": "2015-03-10T00:00:00",
        "analista_cobros_comisiones": "NOMBRE APELLIDO", "gestor": "NOMBRE APELLIDO",
        "analista_riesgos_personas": None,
    }],
}


@router.get(
    "/produccion",
    response_model=ReporteProduccionResponse,
    summary="Reporte de Producción (facturas y notas de crédito/débito por inicio de vigencia)",
    responses={
        200: {"content": {"application/json": {"example": EJEMPLO_RESPUESTA}}},
        400: {"description": "fecha_desde es mayor que fecha_hasta"},
        500: {"description": "Error al generar el reporte (detalle solo en el log del servidor)"},
    },
)
def get_reporte_produccion(
    fecha_desde: date = Query(..., description="Inicio de vigencia desde, formato YYYY-MM-DD"),
    fecha_hasta: date = Query(..., description="Inicio de vigencia hasta, inclusive, formato YYYY-MM-DD"),
    moneda: Optional[str] = Query(
        None, min_length=1, max_length=3,
        description="Moneda del documento: RD o US. Omitida = todas (el reporte original se emite por moneda)"
    ),
    limit: Optional[int] = Query(
        None, ge=1,
        description="Máximo de filas a devolver. Omitido = todas (el reporte original no pagina; ~950 filas por mes)"
    ),
    offset: int = Query(0, ge=0, description="Filas a saltar (usar junto con limit)"),
    username: str = Depends(verify_credentials),
):
    """
    Reporte de Producción: **facturas, notas de crédito y notas de débito** con
    inicio de vigencia entre `fecha_desde` y `fecha_hasta` (ambas inclusive),
    opcionalmente de una sola `moneda`. `tipo_documento` indica qué es cada fila.

    - **FACTURA** (`imfact`): una fila por factura, filtrada por `dinivigen`.
    - **NOTA_CREDITO** / **NOTA_DEBITO** (`imrecibo`): una fila por cada factura
      a la que se aplica la nota; la prima va sin impuesto, en negativo para las
      de crédito. Si la nota no tiene inicio de vigencia se usa la fecha del recibo.

    Los 14 roles de personal son los asignados a la **póliza** (`impolejec`).

    `prima_neta_cobrada`, `creditos_aplicados`, `comision_liquidada`,
    `sobrecomis_liquidada` y `porcentaje_comis_recibo` solo aplican a facturas;
    en las notas van en 0 / null.

    Orden: código de cliente, inicio de vigencia, número de documento.
    """
    if fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=400,
            detail="fecha_desde no puede ser mayor que fecha_hasta.",
        )

    moneda = moneda.strip().upper() if moneda else None
    filtros = ReporteProduccionFiltros(
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, moneda=moneda, limit=limit, offset=offset
    )
    hasta_exclusivo = fecha_hasta + timedelta(days=1)
    params_base = [fecha_desde, hasta_exclusivo, fecha_desde, hasta_exclusivo]
    where = ""
    if moneda:
        where = " WHERE d.moneda = ?"
        params_base.append(moneda)

    conn = None
    try:
        conn = get_db_connection()
        conn.timeout = QUERY_TIMEOUT_SECONDS
        cursor = conn.cursor()

        cursor.execute(f"{DOCS_CTE} SELECT COUNT(*) {BASE_FROM} {where}", params_base)
        total = cursor.fetchone()[0]

        # d.tipo_doc y d.clave como desempate para que la paginación sea estable
        query = (
            f"{DOCS_CTE} {BASE_SELECT} {BASE_FROM} {where} "
            "ORDER BY cli.inumclient, d.inicio_vigencia, d.factura, d.tipo_doc, d.clave"
        )
        params = list(params_base)
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

        return ReporteProduccionResponse(total=total, filtros=filtros, data=data)

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
