from pydantic import BaseModel
from typing import Optional


class AseguradoraRow(BaseModel):
    """
    Una aseguradora (imciaseg) con datos de contacto, estatus y cantidad de pólizas (impoliza).
    Todos los campos son opcionales para que la serialización nunca falle por NULLs.
    """
    codigo: Optional[str] = None             # imciaseg.ccodciaseg
    siglas: Optional[str] = None             # imciaseg.csiglas
    nombre: Optional[str] = None             # imciaseg.cnombre
    estatus: Optional[str] = None            # imciaseg.cestatus ('A' -> 'Activa'; otros códigos tal cual, p. ej. 'I')
    rnc: Optional[str] = None                # imciaseg.crnc
    email: Optional[str] = None              # imciaseg.cemail
    telefono: Optional[str] = None           # imciaseg.cnumtel1
    atencion: Optional[str] = None           # imciaseg.catencion
    cod_intermediario: Optional[str] = None  # imciaseg.codIntermediario
    total_polizas: Optional[int] = None      # COUNT(impoliza.ccodpoliza), todas las versiones


class PaginatedAseguradoraResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[AseguradoraRow]


class AseguradoraRamoRow(BaseModel):
    """
    Cantidad de pólizas (impoliza) por aseguradora, ramo (imramos) y subramo (imsubram).
    Todos los campos son opcionales para que la serialización nunca falle por NULLs.
    """
    cod_aseguradora: Optional[str] = None    # imciaseg.ccodciaseg
    aseguradora: Optional[str] = None        # imciaseg.csiglas
    ramo: Optional[str] = None               # imramos.cdescripcion
    sub_ramo: Optional[str] = None           # imsubram.cdescripcion
    total_polizas: Optional[int] = None      # COUNT(*) de impoliza, todas las versiones
    polizas_vigentes: Optional[int] = None   # impoliza.dfinvigenc >= hoy, todas las versiones


class PaginatedAseguradoraRamoResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[AseguradoraRamoRow]
