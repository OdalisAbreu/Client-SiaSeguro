from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class ReporteProduccionRow(BaseModel):
    """
    Una fila del Reporte de Producción = una factura (imfact), o una nota de
    crédito / débito (imrecibo) aplicada a una factura.
    Todos los campos son opcionales: el sistema fuente tiene muchos NULL
    (por ejemplo fecha_produccion / dfechcierreprod).
    """
    tipo_documento: Optional[str] = None                    # FACTURA | NOTA_CREDITO | NOTA_DEBITO
    cod_cliente: Optional[int] = None                       # imclient.inumclient
    cliente: Optional[str] = None                           # imclient.cnomcliente (+ capellidos si es persona)
    grupo_deudor: Optional[str] = None                      # imclient (ccodgrupo) o el propio cliente
    sucursal: Optional[str] = None                          # imsucursal.cdescripcion
    tipo_cliente: Optional[str] = None                      # imtipclient.tipo
    area: Optional[str] = None                              # imarea.cdescripcion
    ramo: Optional[str] = None                              # imsubram.cdescripcion (sub-ramo)
    aseguradora: Optional[str] = None                       # imciaseg.csiglas
    poliza: Optional[str] = None                            # impoliza.cnumpoliza
    moneda: Optional[str] = None                            # impoliza.cmoneda
    inicio_vigencia: Optional[datetime] = None              # imfact.dinivigen / imrecibo.dinivigen o dfechrecibo
    fecha_produccion: Optional[datetime] = None             # imfact.dfechcierreprod
    factura: Optional[str] = None                           # imfact.cnumfact / imrecibo.cnumrecprov
    concepto: Optional[str] = None                          # imfaconc.cdescripcion
    fecha_remision: Optional[date] = None                   # CAST(imfact.dfechenviado AS DATE)
    suma_asegurada: Optional[Decimal] = None                # imfact.ysumaseg / impoliza.ycantaseg en notas
    tasa_facturacion: Optional[Decimal] = None              # impoliza.ytasa
    prima_neta: Optional[Decimal] = None                    # imfact.yprimaneta / aplicado sin impuesto en notas
    porcentaje_comis: Optional[float] = None                # imfact.bporcomisprod / imrecpol.bporcomis en notas
    comision: Optional[Decimal] = None                      # ROUND(prima_neta * porcentaje_comis / 100, 2)
    # Campos de cobros: solo en filas FACTURA (en las notas van en 0 / None).
    porcentaje_comis_recibo: Optional[float] = None         # imrecpol.bporcomis del recibo más reciente
    prima_neta_cobrada: Optional[Decimal] = None            # aplicado por recibos que no son nota de crédito, sin impuesto
    creditos_aplicados: Optional[Decimal] = None            # aplicado desde notas de crédito, sin impuesto
    comision_liquidada: Optional[Decimal] = None            # imrecingdet.comisionrecibida, tipo ingreso 1, sin rechazadas
    porcentaje_sobrecomis: Optional[Decimal] = None         # imfact.ysobrecomision / imrecpol.ysobrecomision en notas
    sobrecomis_liquidada: Optional[Decimal] = None          # imrecingdet.comisionrecibida, tipo ingreso 2, sin rechazadas
    fecha_ingreso_cliente: Optional[datetime] = None        # imclient.fechaCreacionCliente
    frecuencia_facturacion: Optional[str] = None            # imfrefac.cdescripcion
    fecha_emision_poliza: Optional[datetime] = None         # impoliza.dfechemis
    # Personal asignado a la póliza (impolejec + imejecut), por código de rol (imtipejec)
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
    moneda: Optional[str] = None
    limit: Optional[int] = None
    offset: int = 0


class ReporteProduccionResponse(BaseModel):
    total: int
    filtros: ReporteProduccionFiltros
    advertencias: list[str] = []
    data: list[ReporteProduccionRow]
