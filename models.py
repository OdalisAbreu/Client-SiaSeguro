from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClientResponse(BaseModel):
    id_client: Optional[str] = None
    tipo_tercero_tomador: Optional[int] = None
    tipo_tercero_asegurado: Optional[int] = None
    tipo_tercero_beneficiario: Optional[int] = None
    tipo_tercero_afianzado: Optional[int] = None
    tipo_tercero_proveedor: Optional[int] = None
    tipo_tercero_empleado: Optional[int] = None
    tipo_tercero_apoderado: Optional[int] = None
    sucursal: Optional[str] = None
    cedula: Optional[str] = None
    fecha_vencimiento: Optional[datetime] = None
    rnc: Optional[str] = None
    pasaporte: Optional[str] = None
    registro_mercatil: Optional[str] = None
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    sexo: Optional[str] = None
    tipo_telefono: Optional[str] = None
    numero_telefono: Optional[str] = None
    correo_electronico: Optional[str] = None
    tipo_cliente: Optional[str] = None
    fecha_nacimiento: Optional[datetime] = None
    ciudad_nacimiento: Optional[str] = None
    porvincia_nacimiento: Optional[str] = None
    nacionalidad: Optional[str] = None
    profesion: Optional[str] = None
    ocupacion: Optional[str] = None
    empresa: Optional[str] = None
    dirreccion_lavoral: Optional[str] = None
    ciudad_oficina: Optional[str] = None
    provincia_empresa: Optional[str] = None
    telefono_empresa: Optional[str] = None
    ciudad_recidencia: Optional[str] = None
    provincia_recidiencia: Optional[str] = None
    pais_recidencia: Optional[str] = None
    dirreccion_recidencia: Optional[str] = None
    sector: Optional[str] = None
    autorizo_envio_correo: Optional[int] = None
    autorizo_envio_domicilio: Optional[int] = None
    autorizo_envio_oficina_principal: Optional[int] = None
    autorizo_envio_recidencia: Optional[int] = None
    autorizo_envio_trabajo: Optional[int] = None
    actividad_economica: Optional[str] = None
    ingesos_mensuales: Optional[str] = None
    otros_ingresos: Optional[str] = None
    otros_ingresos_actividad: Optional[str] = None
    recursos_publicos: Optional[str] = None
    recursos_publicos_descripcion: Optional[str] = None
    poder_publico: Optional[str] = None
    poder_publico_descripcion: Optional[str] = None
    influencia_publica: Optional[str] = None
    influencia_publica_descripcion: Optional[str] = None
    afirmativo_familia: Optional[str] = None
    afirmativo_familia_descripcion: Optional[str] = None
    solicitud_seguro_persona: Optional[int] = None
    solicitud_seguro_generales: Optional[int] = None
    solicitud_seguro_fianza: Optional[int] = None
    solicitud_seguro_otros: Optional[str] = None
    ponderacion: Optional[float] = None
    es_procpecto: Optional[str] = None

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
    tipo_tercero_tomador: Optional[int] = None
    tipo_tercero_asegurado: Optional[int] = None
    tipo_tercero_beneficiario: Optional[int] = None
    tipo_tercero_afianzado: Optional[int] = None
    tipo_tercero_proveedor: Optional[int] = None
    tipo_tercero_empleado: Optional[int] = None
    tipo_tercero_apoderado: Optional[int] = None
    sucursal: Optional[str] = None
    cedula: Optional[str] = None
    fecha_vencimiento: Optional[datetime] = None
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    rnc: Optional[str] = None
    pasaporte: Optional[str] = None
    registro_mercatil: Optional[str] = None
    tipo_telefono: Optional[str] = None
    tipo_cliente: Optional[str] = None
    numero_telefono: Optional[str] = None
    correo_electronico: Optional[str] = None
    sexo: Optional[str] = None
    fecha_nacimiento: Optional[datetime] = None
    ciudad_nacimiento: Optional[str] = None
    porvincia_nacimiento: Optional[str] = None
    nacionalidad: Optional[str] = None
    profesion: Optional[str] = None
    ocupacion: Optional[str] = None
    empresa: Optional[str] = None
    dirreccion_lavoral: Optional[str] = None
    ciudad_oficina: Optional[str] = None
    provincia_empresa: Optional[str] = None
    telefono_empresa: Optional[str] = None
    ciudad_recidencia: Optional[str] = None
    provincia_recidiencia: Optional[str] = None
    pais_recidencia: Optional[str] = None
    dirreccion_recidencia: Optional[str] = None
    sector: Optional[str] = None
    autorizo_envio_correo: Optional[int] = None
    autorizo_envio_domicilio: Optional[int] = None
    autorizo_envio_oficina_principal: Optional[int] = None
    autorizo_envio_recidencia: Optional[int] = None
    autorizo_envio_trabajo: Optional[int] = None
    actividad_economica: Optional[str] = None
    ingesos_mensuales: Optional[str] = None
    otros_ingresos: Optional[str] = None
    otros_ingresos_actividad: Optional[str] = None
    recursos_publicos: Optional[str] = None
    recursos_publicos_descripcion: Optional[str] = None
    poder_publico: Optional[str] = None
    poder_publico_descripcion: Optional[str] = None
    influencia_publica: Optional[str] = None
    influencia_publica_descripcion: Optional[str] = None
    afirmativo_familia: Optional[str] = None
    afirmativo_familia_descripcion: Optional[str] = None
    solicitud_seguro_persona: Optional[int] = None
    solicitud_seguro_generales: Optional[int] = None
    solicitud_seguro_fianza: Optional[int] = None
    solicitud_seguro_otros: Optional[str] = None
    ponderacion: Optional[float] = None
    es_procpecto: Optional[str] = None
    fecha_venc_form: Optional[datetime] = None
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

