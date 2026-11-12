from pydantic import BaseModel
from typing import Optional


class EjecutivoCuentaRow(BaseModel):
    """
    Un ejecutivo de cuenta activo (imejecut.cestatus = 'A') por rol (imtipejec),
    con la cantidad de clientes que tiene asignados activamente
    (imcliejec.tfechanulo IS NULL).
    Todos los campos son opcionales para que la serialización nunca falle por NULLs.
    """
    cod_ejecutivo: Optional[str] = None                 # imejecut.ccodejecut
    area: Optional[str] = None                          # calculada a partir de imtipejec.ccodtipejec
    cod_rol: Optional[str] = None                       # imtipejec.ccodtipejec
    rol: Optional[str] = None                           # imtipejec.cdescripcion
    ejecutivo: Optional[str] = None                     # imejecut.cnombres + ' ' + imejecut.capellidos
    estatus: Optional[str] = None                       # imejecut.cestatus ('A' activo)
    es_empleado: Optional[bool] = None                  # imejecut.esEmpleado (1 = empleado interno, 0 = externo/agente)
    cantidad_clientes_asignados: Optional[int] = None   # COUNT(DISTINCT imcliejec.ccodclien)


class PaginatedEjecutivoCuentaResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    data: list[EjecutivoCuentaRow]
