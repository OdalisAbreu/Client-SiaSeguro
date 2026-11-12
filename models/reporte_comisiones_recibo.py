from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


ADVERTENCIA_AGENTE_NO_VALIDADO = (
    "agente_poliza y porcentaje_incentivo_agente no están validados contra un caso real; "
    "revisar si el ambiente de producción tiene datos en ST_ProPago / vw_Comis_Generada.Agente "
    "para resolverlo de forma definitiva"
)

ADVERTENCIA_CAMPOS_BAJA_CONFIANZA = (
    "gastos_admin, prima_neta (aproximación), comision_liquidada, diferencia, "
    "sobrecomis_liquidada y sobrecomis_diferencia no están validados contra el reporte original; "
    "comision_liquidada (imrecpol.ycomisrecibida) no coincidió con casos reales"
)


class ReporteComisionesReciboRow(BaseModel):
    """
    Una fila = un recibo aplicado a factura (imrecpol), con la coaseguradora de
    mayor participación de la factura (imfactcoaseg) o, si la factura no tiene
    coaseguro declarado, la aseguradora líder de la póliza al 100%.
    """
    cod_cliente: Optional[int] = None                       # imclient.inumclient
    cliente: Optional[str] = None                           # imclient.cnomcliente
    grupo_deudor: Optional[str] = None                      # imclient (ccodgrupo) o el propio cliente
    sucursal: Optional[str] = None                          # imsucursal.cdescripcion
    tipo_cliente: Optional[str] = None                      # imtipclient.tipo
    fecha_cliente: Optional[datetime] = None                # imclient.dfechingreso
    area: Optional[str] = None                              # imarea.cdescripcion
    ramo: Optional[str] = None                              # imramos.cdescripcion
    fecha_emision: Optional[datetime] = None                # impoliza.dfechemis
    poliza: Optional[str] = None                            # impoliza.cnumpoliza
    aseguradora: Optional[str] = None                       # imciaseg.cnombre (líder de la póliza)
    coaseguro: Optional[str] = None                         # imciaseg.cnombre (imfactcoaseg de mayor nporcpart o líder)
    porcentaje_participacion: Optional[Decimal] = None      # imfactcoaseg.nporcpart (la mayor) o 100
    moneda: Optional[str] = None                            # impoliza.cmoneda
    recibo: Optional[str] = None                            # imrecibo.cnumrecprov
    concepto_recibo: Optional[str] = None                   # imfaconc.cdescripcion (imrecibo.ccodfaconc)
    forma_pago: Optional[str] = None                        # imfrmpag.cdescripcion
    fecha_recibo: Optional[datetime] = None                 # imrecibo.dfechrecibo
    fecha_registro: Optional[datetime] = None               # imrecibo.tfechregistro
    factura: Optional[str] = None                           # imfact.cnumfact
    inicio_vig_factura: Optional[datetime] = None           # imfact.dinivigen
    dias: Optional[int] = None                              # DATEDIFF(DAY, dinivigen, dfechrecibo)
    concepto: Optional[str] = None                          # imfaconc.cdescripcion (imfact.ccodfaconc)
    gastos_admin: Optional[Decimal] = None                  # imfact.ygadministrativo (BAJA CONFIANZA: no validado)
    prima_bruta: Optional[Decimal] = None                   # imrecpol.yaplicado (monto aplicado por este recibo)
    prima_neta: Optional[Decimal] = None                    # yaplicado / (1 + imfact.bporcimp / 100) (APROXIMACIÓN, no validado)
    mantiene_porcentaje_comis: Optional[str] = None         # impoliza.mantenerporcomis -> "Si" / ""
    recibo_comisiones: Optional[int] = None                 # imrecing.inumrecing (null si no liquidada)
    porcentaje_comis: Optional[float] = None                # imrecpol.bporcomis
    comision_generada: Optional[Decimal] = None             # ROUND(prima_neta * bporcomis / 100, 2)
    comision_liquidada: Optional[Decimal] = None            # imrecpol.ycomisrecibida (BAJA CONFIANZA: no coincidió con casos reales)
    diferencia: Optional[Decimal] = None                    # comision_generada - comision_liquidada (BAJA CONFIANZA)
    porcentaje_sobrecomis: Optional[Decimal] = None         # imrecpol.ysobrecomision
    sobrecomis_generada: Optional[Decimal] = None           # ROUND(prima_neta * ysobrecomision / 100, 2)
    sobrecomis_liquidada: Optional[Decimal] = None          # BAJA CONFIANZA: no validado
    sobrecomis_diferencia: Optional[Decimal] = None         # sobrecomis_generada - sobrecomis_liquidada (BAJA CONFIANZA)
    agente_poliza: Optional[str] = None                     # NO VALIDADO (imcocorretaje / cocorredores)
    porcentaje_incentivo_agente: Optional[Decimal] = None   # NO VALIDADO
    analista_cobros_comisiones: Optional[str] = None        # imejecut vía impolejec (ccodtipejec '002')


class ReporteComisionesReciboFiltros(BaseModel):
    fecha_desde: date
    fecha_hasta: date
    cliente: Optional[str] = None
    analista: Optional[str] = None
    sucursal: Optional[str] = None
    area: Optional[str] = None
    tipo_cliente: Optional[str] = None
    aseguradora: Optional[str] = None
    ramo: Optional[list[str]] = None
    moneda: Optional[str] = None
    limit: Optional[int] = None
    offset: int = 0


class ReporteComisionesReciboResponse(BaseModel):
    total: int
    filtros: ReporteComisionesReciboFiltros
    advertencias: list[str] = []
    data: list[ReporteComisionesReciboRow]
