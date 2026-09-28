from pydantic import BaseModel, field_serializer
from typing import Optional
from datetime import datetime
from decimal import Decimal


class ImClient(BaseModel):
    """
    Modelo que refleja todos los campos de la tabla imclient (72 columnas).
    PK: ccodclien
    Generado a partir del esquema real de SQL Server (INFORMATION_SCHEMA).
    Todos los campos son opcionales para que la serializacion de la respuesta
    nunca falle por valores NULL o inesperados que devuelva la base de datos.
    """
    ccodclien: Optional[str] = None                     # char(8) NOT NULL - PK
    icodclien: Optional[int] = None                     # int NOT NULL
    inumclient: Optional[int] = None                    # int NOT NULL
    cnomcliente: Optional[str] = None                   # char(125) NOT NULL
    cgrupempr: Optional[str] = None                     # char(30) NOT NULL
    ctitcortesia: Optional[str] = None                  # char(2) NOT NULL
    crnc: Optional[str] = None                          # char(14) NOT NULL
    cpasaporte: Optional[str] = None                    # nvarchar(max) NULL
    cnacional: Optional[str] = None                     # char(35) NOT NULL
    dfechnac: Optional[datetime] = None                 # datetime NULL
    ccedula: Optional[str] = None                       # char(14) NOT NULL
    cdirecofi1: Optional[str] = None                    # char(75) NOT NULL
    cdirecofi2: Optional[str] = None                    # char(75) NOT NULL
    cdirecofi3: Optional[str] = None                    # char(75) NOT NULL
    ccodciudadofi: Optional[str] = None                 # char(8) NOT NULL
    ccodpaisofi: Optional[str] = None                   # char(8) NOT NULL
    clocalidadofi: Optional[str] = None                 # char(20) NOT NULL
    cdireccas1: Optional[str] = None                    # char(75) NOT NULL
    cdireccas2: Optional[str] = None                    # char(75) NOT NULL
    cdireccas3: Optional[str] = None                    # char(75) NOT NULL
    ccodciudadcas: Optional[str] = None                 # char(8) NOT NULL
    ccodpaiscas: Optional[str] = None                   # char(8) NOT NULL
    ctipotel1: Optional[str] = None                     # char(8) NOT NULL
    cnumtel1: Optional[str] = None                      # char(17) NOT NULL
    ctipotel2: Optional[str] = None                     # char(8) NOT NULL
    cnumtel2: Optional[str] = None                      # char(17) NOT NULL
    ctipotel3: Optional[str] = None                     # char(8) NOT NULL
    cnumtel3: Optional[str] = None                      # char(17) NOT NULL
    ctipotel4: Optional[str] = None                     # char(8) NOT NULL
    cnumtel4: Optional[str] = None                      # char(17) NOT NULL
    ctipotel5: Optional[str] = None                     # char(8) NOT NULL
    cnumtel5: Optional[str] = None                      # char(17) NOT NULL
    ctipotel6: Optional[str] = None                     # char(8) NOT NULL
    cnumtel6: Optional[str] = None                      # char(17) NOT NULL
    cemail1: Optional[str] = None                       # nvarchar(max) NULL
    cemail2: Optional[str] = None                       # nvarchar(max) NULL
    ccodactiv: Optional[str] = None                     # char(6) NOT NULL
    dfechingreso: Optional[datetime] = None             # datetime NULL
    dfechefect: Optional[datetime] = None               # datetime NULL
    cprospecto: Optional[str] = None                    # char(1) NOT NULL
    ybalance: Optional[Decimal] = None                  # money NOT NULL
    catencion: Optional[str] = None                     # char(8) NOT NULL
    cwebpage: Optional[str] = None                      # char(100) NOT NULL
    cstatus: Optional[str] = None                       # char(2) NOT NULL
    lcompania: Optional[bool] = None                    # bit NOT NULL
    mcomentario: Optional[str] = None                   # text NOT NULL
    ctitucor: Optional[str] = None                      # char(10) NOT NULL
    icorrespondencia: Optional[int] = None              # int NOT NULL
    ccodgrupo: Optional[str] = None                     # char(8) NOT NULL
    icompania: Optional[int] = None                     # int NOT NULL
    capellidos: Optional[str] = None                    # char(40) NOT NULL
    ccodagente: Optional[str] = None                    # char(8) NOT NULL
    ccodejecuent: Optional[str] = None                  # char(8) NOT NULL
    ccodejecobro: Optional[str] = None                  # char(8) NOT NULL
    timestamp_column: Optional[bytes] = None            # timestamp (rowversion) NULL
    ccodcliact: Optional[str] = None                    # char(8) NOT NULL
    ccodtitulo: Optional[str] = None                    # char(8) NOT NULL
    ccodsectorfin: Optional[str] = None                 # char(8) NOT NULL
    ccodnacion: Optional[str] = None                    # char(8) NOT NULL
    ccodprovinciacas: Optional[str] = None              # char(8) NOT NULL
    ccodseccioncas: Optional[str] = None                # char(8) NOT NULL
    ccodbarrioparajecas: Optional[str] = None           # char(8) NOT NULL
    ccodprovinciaofi: Optional[str] = None              # char(8) NOT NULL
    ccodseccionofi: Optional[str] = None                # char(8) NOT NULL
    ccodbarrioparajeofi: Optional[str] = None           # char(8) NOT NULL
    fechaCreacionCliente: Optional[datetime] = None     # datetime NULL
    fechaCreacionProspecto: Optional[datetime] = None   # datetime NULL
    userIdcreacioncliente: Optional[str] = None         # nvarchar(max) NULL
    userIdcreacionprospecto: Optional[str] = None       # nvarchar(max) NULL
    txt_dir1Postal: Optional[str] = None                # nvarchar(max) NULL
    txt_dir2Postal: Optional[str] = None                # nvarchar(max) NULL
    ccodfrmpag: Optional[str] = None                    # nvarchar(8) NULL

    @field_serializer("timestamp_column")
    def serialize_timestamp_column(self, value: Optional[bytes]) -> Optional[str]:
        # rowversion es binario arbitrario; no se puede decodificar como UTF-8
        return value.hex() if value is not None else None

    class Config:
        from_attributes = True


class PaginatedImClientResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[ImClient]


class ImClientConTipo(ImClient):
    """
    Extiende ImClient agregando el tipo de cliente y la sucursal.

    Ninguno de los dos vive en imclient: se obtienen encadenando
    imclient.ccodclien -> imclientdet.ccodclien y desde ahi
    imclientdet.imtipclientid -> imtipclient.imtipclientid
    imclientdet.ccodsucursal  -> imsucursal.ccodsucursal

    Todos son opcionales porque hay registros en imclientdet con
    imtipclientid nulo (sin tipo) y con ccodsucursal nulo (sin sucursal).
    """
    imtipclientid: Optional[int] = None                 # imclientdet.imtipclientid
    tipo_cliente: Optional[str] = None                  # imtipclient.tipo
    ccodsucursal: Optional[str] = None                  # imclientdet.ccodsucursal
    sucursal: Optional[str] = None                      # imsucursal.cdescripcion


class PaginatedImClientConTipoResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[ImClientConTipo]
