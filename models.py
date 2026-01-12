from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClientResponse(BaseModel):
    id_client: Optional[str] = None
    cod_client: Optional[int] = None
    num_client: Optional[int] = None
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    cedula: Optional[str] = None
    rnc: Optional[str] = None
    estatus: Optional[str] = None
    dirreccion_1: Optional[str] = None
    dirreccion_2: Optional[str] = None
    dirreccion_3: Optional[str] = None
    dirreccion_casa_1: Optional[str] = None
    dirreccion_casa_2: Optional[str] = None
    dirreccion_casa_3: Optional[str] = None
    tipo_telefono: Optional[str] = None
    tipo_celular_1: Optional[str] = None
    email_1: Optional[str] = None
    email_2: Optional[str] = None
    tipo_cliente: Optional[str] = None
    fecha_nacimiento: Optional[datetime] = None
    fecha_creacion: Optional[datetime] = None
    fecha_ingreso: Optional[datetime] = None
    activa_comercial: Optional[str] = None
    sexo: Optional[str] = None
    profecion: Optional[str] = None
    cargo: Optional[str] = None
    empresa: Optional[str] = None
    ponderacion: Optional[float] = None
    sucursal: Optional[str] = None
    es_procpecto: Optional[str] = None
    telefono_oficina: Optional[str] = None
    numero_celular: Optional[str] = None

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[ClientResponse]


class Credentials(BaseModel):
    username: str
    password: str


class KYCResponse(BaseModel):
    id_client: Optional[str] = None
    cod_client: Optional[int] = None
    num_client: Optional[int] = None
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    rnc: Optional[str] = None
    pasporrte: Optional[str] = None
    fecha_nacimiento: Optional[datetime] = None
    cedula: Optional[str] = None
    dirreccion_1: Optional[str] = None
    dirreccion_2: Optional[str] = None
    dirreccion_3: Optional[str] = None
    dirreccion_casa_1: Optional[str] = None
    dirreccion_casa_2: Optional[str] = None
    dirreccion_casa_3: Optional[str] = None
    tipo_telefono: Optional[str] = None
    num_telefono: Optional[str] = None
    tipo_celular_1: Optional[str] = None
    num_celular_2: Optional[str] = None
    email_1: Optional[str] = None
    email_2: Optional[str] = None
    fecha_ingreso: Optional[datetime] = None
    fecha_creacion_cliente: Optional[datetime] = None
    fecha_creacion_prospecto: Optional[datetime] = None
    ccodsucursal: Optional[str] = None
    fecha_remision_formulario: Optional[datetime] = None
    fecha_recepcion_formulario: Optional[datetime] = None
    fecha_venc_form: Optional[datetime] = None
    formremitido: Optional[int] = None
    formrecibido: Optional[int] = None
    estado_formulario: Optional[str] = None
    dias_hasta_vencimiento: Optional[int] = None

    class Config:
        from_attributes = True


class TotalesPorEstado(BaseModel):
    vigente: int = 0
    vencido: int = 0
    vencido_no_remitido: int = 0
    pendiente_de_remision: int = 0
    sin_clasificar: int = 0


class PaginatedKYCResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[KYCResponse]
    totales_por_estado: TotalesPorEstado

