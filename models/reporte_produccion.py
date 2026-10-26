from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


ADVERTENCIA_CAMPOS_ESTIMADOS = (
    "prima_neta_cobrada, creditos_aplicados, comision_liquidada y sobrecomis_liquidada "
    "son valores estimados, pendientes de validar contra el reporte original"
)


class ReporteProduccionRow(BaseModel):
    """
    Una fila del Reporte de Producción = una factura (imfact).
    Todos los campos son opcionales: el sistema fuente tiene muchos NULL
    (por ejemplo fecha_produccion / dfechcierreprod).
    """
    cod_cliente: Optional[int] = None                       # imclient.inumclient
    cliente: Optional[str] = None                           # imclient.cnomcliente
    grupo_deudor: Optional[str] = None                      # imclient (ccodgrupo) o el propio cliente
    sucursal: Optional[str] = None                          # imsucursal.cdescripcion
    tipo_cliente: Optional[str] = None                      # imtipclient.tipo
    area: Optional[str] = None                              # imarea.cdescripcion
    ramo: Optional[str] = None                              # imramos.cdescripcion
    aseguradora: Optional[str] = None                       # imciaseg.cnombre
    poliza: Optional[str] = None                            # impoliza.cnumpoliza
    moneda: Optional[str] = None                            # impoliza.cmoneda
    inicio_vigencia: Optional[datetime] = None              # imfact.dinivigen
    fecha_produccion: Optional[datetime] = None             # imfact.dfechcierreprod
    factura: Optional[str] = None                           # imfact.cnumfact
    concepto: Optional[str] = None                          # imfaconc.cdescripcion
    fecha_remision: Optional[date] = None                   # CAST(imfact.dfechenviado AS DATE)
    suma_asegurada: Optional[Decimal] = None                # imfact.ysumaseg
    tasa_facturacion: Optional[Decimal] = None              # impoliza.ytasa
    prima_neta: Optional[Decimal] = None                    # imfact.yprimaneta
    porcentaje_comis: Optional[float] = None                # imfact.bporcomisprod
    comision: Optional[Decimal] = None                      # ROUND(prima_neta * porcentaje_comis / 100, 2)
    prima_neta_cobrada: Optional[Decimal] = None            # ESTIMADO
    creditos_aplicados: Optional[Decimal] = None            # ESTIMADO
    comision_liquidada: Optional[Decimal] = None            # ESTIMADO
    porcentaje_sobrecomis: Optional[Decimal] = None         # imfact.ysobrecomision
    sobrecomis_liquidada: Optional[Decimal] = None          # ESTIMADO
    fecha_ingreso_cliente: Optional[datetime] = None        # imclient.dfechingreso
    frecuencia_facturacion: Optional[str] = None            # imfrefac.cdescripcion
    fecha_emision_poliza: Optional[datetime] = None         # impoliza.dfechemis
    # Personal asignado al cliente (imcliejec + imejecut), por código de rol (imtipejec)
    analista_cobros_comisiones: Optional[str] = None        # 002
    analista_riesgos_personas: Optional[str] = None         # 006
    analista_riesgos_generales: Optional[str] = None        # 00000001
    analista_riesgos_internacionales: Optional[str] = None  # 00000003
    analista_rg_emision: Optional[str] = None               # 00000018
    analista_rg_movimientos: Optional[str] = None           # 00000019
    analista_rg_renovacion: Optional[str] = None            # 00000017
    asesor_reclamaciones_int: Optional[str] = None          # 00000004
    asesor_reclamaciones_rg: Optional[str] = None           # 00000002
    asesor_reclamaciones_rp: Optional[str] = None           # 004
    gestor: Optional[str] = None                            # 003
    gestor_cuentas_rg: Optional[str] = None                 # 00000005
    gestor_cuentas_ri: Optional[str] = None                 # 00000009
    gestor_cuentas_rp: Optional[str] = None                 # 001


class ReporteProduccionFiltros(BaseModel):
    fecha_desde: date
    fecha_hasta: date
    limit: Optional[int] = None
    offset: int = 0


class ReporteProduccionResponse(BaseModel):
    total: int
    filtros: ReporteProduccionFiltros
    advertencias: list[str] = []
    data: list[ReporteProduccionRow]
