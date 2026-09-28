from pydantic import BaseModel, field_serializer
from typing import Optional
from datetime import datetime
from decimal import Decimal


class ImPoliza(BaseModel):
    """
    Modelo que refleja todos los campos de la tabla impoliza (66 columnas).
    PK: ccodpoliza
    Poliza activa: ccodpolsta = '00000001'.
    Generado a partir del esquema real de SQL Server (INFORMATION_SCHEMA).
    Todos los campos son opcionales para que la serializacion de la respuesta
    nunca falle por valores NULL o inesperados que devuelva la base de datos.
    """
    ccodpoliza: Optional[str] = None                    # char(8) NOT NULL - PK
    icodpoliza: Optional[int] = None                    # int NOT NULL
    cnumpoliza: Optional[str] = None                    # char(20) NOT NULL
    creferencia: Optional[str] = None                   # char(20) NOT NULL
    ccodclien: Optional[str] = None                     # char(8) NOT NULL
    ccodciaseg: Optional[str] = None                    # char(8) NOT NULL
    ccodsubram: Optional[str] = None                    # char(8) NOT NULL
    dfechemis: Optional[datetime] = None                # datetime NULL
    dinivigenc: Optional[datetime] = None               # datetime NULL
    dfinvigenc: Optional[datetime] = None               # datetime NULL
    ccodfrefac: Optional[str] = None                    # char(8) NOT NULL
    icantasegs: Optional[int] = None                    # int NOT NULL
    bporcomis: Optional[float] = None                   # float NOT NULL
    ccodpolsta: Optional[str] = None                    # char(8) NOT NULL (estado)
    dfechstatus: Optional[datetime] = None              # datetime NULL
    mcomentario: Optional[str] = None                   # text NOT NULL
    bporcimp: Optional[float] = None                    # float NOT NULL
    ymontoimp: Optional[Decimal] = None                 # money NOT NULL
    yprimaneta: Optional[Decimal] = None                # money NOT NULL
    yprimabruta: Optional[Decimal] = None               # money NOT NULL
    ycantaseg: Optional[Decimal] = None                 # money NOT NULL
    ccodpolizaversion: Optional[str] = None             # char(8) NOT NULL
    ccodvercon: Optional[str] = None                    # char(8) NOT NULL
    mcomversion: Optional[str] = None                   # text NOT NULL
    lversionactual: Optional[bool] = None               # bit NOT NULL
    mclausulas: Optional[str] = None                    # text NOT NULL
    mendosos: Optional[str] = None                      # text NOT NULL
    cagenteid: Optional[str] = None                     # char(8) NOT NULL
    cejecuenid: Optional[str] = None                    # char(8) NOT NULL
    cejecobroid: Optional[str] = None                   # char(8) NOT NULL
    usr_pk: Optional[str] = None                        # char(5) NOT NULL
    tfechregistro: Optional[datetime] = None            # datetime NULL
    ccodsolicitud: Optional[str] = None                 # nvarchar(255) NULL
    tfechfisica: Optional[datetime] = None              # datetime NULL
    usr_fisica: Optional[str] = None                    # char(5) NOT NULL
    cmoneda: Optional[str] = None                       # char(2) NOT NULL
    idiafactura: Optional[int] = None                   # int NOT NULL
    idiacorte: Optional[int] = None                     # int NOT NULL
    ccodultfact: Optional[str] = None                   # char(8) NOT NULL
    timestamp_column: Optional[bytes] = None            # timestamp (rowversion) NULL
    ccodplanisi: Optional[str] = None                   # char(8) NULL
    yprimaexcesoisi: Optional[Decimal] = None           # money NOT NULL
    iejecmaxcomis: Optional[int] = None                 # int NULL
    bcomispriexc: Optional[float] = None                # float NOT NULL
    ytasa: Optional[Decimal] = None                     # money NOT NULL
    ysobrecomision: Optional[Decimal] = None            # money NOT NULL
    ygadministrativo: Optional[Decimal] = None          # money NOT NULL
    norenovable: Optional[bool] = None                  # bit NOT NULL
    notifRen: Optional[bool] = None                     # bit NOT NULL
    notifVenc: Optional[bool] = None                    # bit NOT NULL
    mantenerporcomis: Optional[bool] = None             # bit NOT NULL
    PrimaMinima: Optional[Decimal] = None               # money NOT NULL
    ycargoFraccionario: Optional[Decimal] = None        # money NOT NULL
    esmaestra: Optional[bool] = None                    # bit NOT NULL
    relacionmaestra: Optional[str] = None               # nvarchar(max) NULL
    balance: Optional[Decimal] = None                   # decimal(18,2) NOT NULL
    legal: Optional[bool] = None                        # bit NOT NULL
    forma_envio_factura: Optional[str] = None           # nvarchar(max) NULL
    renprov_cotizador_web: Optional[bool] = None        # bit NOT NULL
    acuerdo_cotizador_web: Optional[bool] = None        # bit NOT NULL
    forma_pago_cotizador_web: Optional[str] = None      # nvarchar(max) NULL
    cuotas_cotizador_web: Optional[int] = None          # int NOT NULL
    fecha_pago_cotizador_web: Optional[datetime] = None # datetime NULL
    fondoacumulado: Optional[Decimal] = None            # decimal(18,2) NULL
    CanceladaViaPortal: Optional[bool] = None           # bit NOT NULL
    areaP: Optional[str] = None                         # varchar(200) NULL

    @field_serializer("timestamp_column")
    def serialize_timestamp_column(self, value: Optional[bytes]) -> Optional[str]:
        # rowversion es binario arbitrario; no se puede decodificar como UTF-8
        return value.hex() if value is not None else None

    class Config:
        from_attributes = True


class PaginatedImPolizaResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[ImPoliza]
