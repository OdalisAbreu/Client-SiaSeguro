# Prompt para el proyecto de la API (pegar tal cual)

---

Necesito implementar un endpoint en nuestra API interna que exponga el "Reporte de Producción" del sistema de corretaje de seguros (base de datos SQL Server `SIAsegCaceres`). Ya reconstruí y validé el query SQL necesario contra la base real; tu trabajo es implementarlo como endpoint, reusando los modelos que ya tengo registrados y creando los que falten.

## Contexto del negocio

Es un reporte de producción (pólizas facturadas) por rango de fechas, usado por el área de cobros/comisiones. Grano: **una fila por factura** (tabla `imfact`), con datos del cliente, póliza, aseguradora, montos, y 14 columnas de personal asignado (analistas/gestores/asesores) por cliente.

## Modelos / tablas involucradas

Reutiliza los modelos que ya tengo para estas tablas si existen; si no, créalos (todas en el schema `dbo` de SQL Server):

- `imfact` (facturas) — grano base del reporte
- `impoliza` (pólizas) — join por `ccodpoliza`
- `imclient` (clientes) — join por `ccodclien`; auto-join adicional por `ccodgrupo` (cliente padre, para "Grupo Deudor")
- `imclientdet` (detalle cliente) — join por `ccodclien`, da sucursal y tipo de cliente
- `imsucursal` (catálogo sucursales)
- `imtipclient` (catálogo tipo de cliente: PERSONAL, COMERCIAL, CORPORATIVOS, etc.)
- `imsubram` (subramo) — join por `ccodsubram` desde `impoliza`
- `imramos` (catálogo de ramos) — join por `ccodramo` desde `imsubram`
- `imareram` (mapeo subramo→área) — join por `ccodsubram`
- `imarea` (catálogo de áreas) — join por `ccodarea`
- `imciaseg` (aseguradoras) — join por `ccodciaseg`
- `imfaconc` (catálogo de conceptos de factura) — join por `ccodfaconc`
- `imfrefac` (catálogo de frecuencias de facturación) — join por `ccodfrefac`
- `imcliejec` (asignación cliente↔ejecutivo↔tipo de rol)
- `imtipejec` (catálogo de tipos de rol — ver códigos abajo)
- `imejecut` (datos del ejecutivo/empleado)
- `imrecpol` (aplicación de recibos a facturas) — usado para los campos ESTIMADO, ver nota abajo
- `t_creditos` (créditos aplicados) — usado para Créditos Aplicados (ESTIMADO)

## Endpoint a crear

```
GET /api/reportes/produccion?fecha_desde=YYYY-MM-DD&fecha_hasta=YYYY-MM-DD
```

- `fecha_desde` y `fecha_hasta`: requeridos, filtran por `imfact.dfechfact` (fecha de la factura).
- Validar que `fecha_desde <= fecha_hasta`; si no, 400 con mensaje claro.
- Respuesta: JSON con `{"total": <int>, "filtros": {...}, "data": [ {...fila...}, ... ]}`.
- Pagina si el volumen es grande (sugerido: `limit`/`offset` opcionales, default sin límite ya que el reporte original no pagina, pero evalúa el tamaño esperado — puede haber miles de filas).

## Campos de cada fila (nombres snake_case para el JSON)

```
cod_cliente, cliente, grupo_deudor, sucursal, tipo_cliente, area, ramo,
aseguradora, poliza, moneda, inicio_vigencia, fecha_produccion, factura,
concepto, fecha_remision, suma_asegurada, tasa_facturacion, prima_neta,
porcentaje_comis, comision, prima_neta_cobrada, creditos_aplicados,
comision_liquidada, porcentaje_sobrecomis, sobrecomis_liquidada,
fecha_ingreso_cliente, frecuencia_facturacion, fecha_emision_poliza,
analista_cobros_comisiones, analista_riesgos_personas, analista_riesgos_generales,
analista_riesgos_internacionales, analista_rg_emision, analista_rg_movimientos,
analista_rg_renovacion, asesor_reclamaciones_int, asesor_reclamaciones_rg,
asesor_reclamaciones_rp, gestor, gestor_cuentas_rg, gestor_cuentas_ri, gestor_cuentas_rp
```

## Lógica de cada campo (ya verificada contra datos reales, úsala tal cual)

- `cod_cliente` = `imclient.inumclient`
- `cliente` = `imclient.cnomcliente`
- `grupo_deudor` = nombre del cliente apuntado por `imclient.ccodgrupo` (self-join); si `ccodgrupo` es nulo o no tiene match, usar el propio nombre del cliente
- `sucursal` = `imclientdet.ccodsucursal` → `imsucursal.cdescripcion`
- `tipo_cliente` = `imclientdet.imtipclientid` → `imtipclient.tipo`
- `ramo` = `impoliza.ccodsubram` → `imsubram.ccodramo` → `imramos.cdescripcion`
- `area` = `impoliza.ccodsubram` → `imareram.ccodarea` → `imarea.cdescripcion`
- `aseguradora` = `impoliza.ccodciaseg` → `imciaseg.cnombre`
- `poliza` = `impoliza.cnumpoliza`
- `moneda` = `impoliza.cmoneda`
- `inicio_vigencia` = `imfact.dinivigen`
- `fecha_produccion` = `imfact.dfechcierreprod` (puede venir NULL con frecuencia, es así en el sistema fuente)
- `factura` = `imfact.cnumfact`
- `concepto` = `imfact.ccodfaconc` → `imfaconc.cdescripcion`
- `fecha_remision` = fecha (sin hora) de `imfact.dfechenviado`
- `suma_asegurada` = `imfact.ysumaseg`
- `tasa_facturacion` = `impoliza.ytasa`
- `prima_neta` = `imfact.yprimaneta`
- `porcentaje_comis` = `imfact.bporcomisprod`
- `comision` = `imfact.yprimaneta * imfact.bporcomisprod / 100`, redondeado a 2 decimales
- `porcentaje_sobrecomis` = `imfact.ysobrecomision`
- `fecha_ingreso_cliente` = `imclient.dfechingreso`
- `frecuencia_facturacion` = `impoliza.ccodfrefac` → `imfrefac.cdescripcion`
- `fecha_emision_poliza` = `impoliza.dfechemis`
- Los 14 campos de analistas/gestores: para cada uno, buscar en `imcliejec` el registro con `ccodclien` = cliente de la fila, `ccodtipejec` = código de rol (tabla abajo), y `tfechanulo IS NULL` (activo); traer `imejecut.cnombres + ' ' + imejecut.capellidos`. Si no hay match, `null`.

### Códigos de rol (`imtipejec.ccodtipejec`) para los 14 campos

| Campo | Código |
|---|---|
| analista_cobros_comisiones | `002` |
| analista_riesgos_personas | `006` |
| analista_riesgos_generales | `00000001` |
| analista_riesgos_internacionales | `00000003` |
| analista_rg_emision | `00000018` |
| analista_rg_movimientos | `00000019` |
| analista_rg_renovacion | `00000017` |
| asesor_reclamaciones_int | `00000004` |
| asesor_reclamaciones_rg | `00000002` |
| asesor_reclamaciones_rp | `004` |
| gestor | `003` |
| gestor_cuentas_rg | `00000005` |
| gestor_cuentas_ri | `00000009` |
| gestor_cuentas_rp | `001` |

**Nota de rendimiento**: en el SQL original usé una subquery escalar por cada uno de estos 14 campos (14 subqueries correlacionadas por fila). Si el volumen de filas es alto, considera en su lugar: 1) traer de una sola vez todos los registros de `imcliejec`+`imtipejec`+`imejecut` para el conjunto de clientes de la página actual, agrupados por `ccodclien` y `ccodtipejec` en un diccionario en Python, y 2) hacer el "pivot" en memoria al construir la respuesta, para evitar 14×N queries.

## Campos marcados ESTIMADO — IMPORTANTE, no están 100% validados

Estos 4 campos usan una fórmula que **no coincidió exactamente** contra un caso real del reporte original al validarla (ver detalle abajo). Impleméntalos tal cual por ahora, pero:
- Agrega un campo adicional en la respuesta `advertencias: ["prima_neta_cobrada, creditos_aplicados, comision_liquidada y sobrecomis_liquidada son valores estimados, pendientes de validar contra el reporte original"]` (a nivel de la respuesta general, no por fila, para no inflar el payload).
- Dejar hooks/TODO en el código para facilitar ajustar la fórmula después sin tocar el resto del endpoint.

Fórmulas actuales (mejor esfuerzo, no exactas):

- `prima_neta_cobrada` = `SUM(imrecpol.yaplicado)` donde `imrecpol.ccodfact` = la factura de la fila
- `comision_liquidada` = `SUM(imrecpol.ycomisrecibida)` donde `imrecpol.ccodfact` = la factura de la fila (en la práctica suele dar 0, es el campo más incierto)
- `creditos_aplicados` = `SUM(t_creditos.montooper)` donde `t_creditos.numpoliza` = la póliza y `t_creditos.numfactura` = la factura de la fila, y `t_creditos.anulado = 0`
- `sobrecomis_liquidada`:
  - si `imfact.bporcomisprod != 0`: `comision_liquidada * (imfact.ysobrecomision / imfact.bporcomisprod)`
  - si `imfact.bporcomisprod == 0`: `prima_neta_cobrada * (impoliza.ysobrecomision / 100)`

## Query SQL de referencia (ya probado, corre sin errores)

```sql
SELECT
    cli.inumclient                                      AS cod_cliente,
    cli.cnomcliente                                     AS cliente,
    ISNULL(g.cnomcliente, cli.cnomcliente)              AS grupo_deudor,
    suc.cdescripcion                                    AS sucursal,
    tc.tipo                                             AS tipo_cliente,
    area.cdescripcion                                   AS area,
    ramo.cdescripcion                                   AS ramo,
    aseg.cnombre                                        AS aseguradora,
    pol.cnumpoliza                                      AS poliza,
    pol.cmoneda                                         AS moneda,
    f.dinivigen                                         AS inicio_vigencia,
    f.dfechcierreprod                                   AS fecha_produccion,
    f.cnumfact                                          AS factura,
    conc.cdescripcion                                   AS concepto,
    CAST(f.dfechenviado AS DATE)                        AS fecha_remision,
    f.ysumaseg                                          AS suma_asegurada,
    pol.ytasa                                           AS tasa_facturacion,
    f.yprimaneta                                        AS prima_neta,
    f.bporcomisprod                                     AS porcentaje_comis,
    ROUND(f.yprimaneta * f.bporcomisprod / 100.0, 2)    AS comision,
    f.ysobrecomision                                    AS porcentaje_sobrecomis,
    cli.dfechingreso                                    AS fecha_ingreso_cliente,
    frec.cdescripcion                                   AS frecuencia_facturacion,
    pol.dfechemis                                       AS fecha_emision_poliza
FROM dbo.imfact f
JOIN dbo.impoliza pol          ON pol.ccodpoliza = f.ccodpoliza
JOIN dbo.imclient cli          ON cli.ccodclien  = pol.ccodclien
LEFT JOIN dbo.imclient g       ON g.ccodclien    = cli.ccodgrupo
LEFT JOIN dbo.imclientdet cdet ON cdet.ccodclien = cli.ccodclien
LEFT JOIN dbo.imsucursal suc   ON suc.ccodsucursal = cdet.ccodsucursal
LEFT JOIN dbo.imtipclient tc   ON tc.imtipclientid = cdet.imtipclientid
JOIN dbo.imsubram sub          ON sub.ccodsubram = pol.ccodsubram
JOIN dbo.imramos ramo          ON ramo.ccodramo  = sub.ccodramo
LEFT JOIN dbo.imareram ar      ON ar.ccodsubram  = sub.ccodsubram
LEFT JOIN dbo.imarea area      ON area.ccodarea  = ar.ccodarea
JOIN dbo.imciaseg aseg         ON aseg.ccodciaseg = pol.ccodciaseg
LEFT JOIN dbo.imfaconc conc    ON conc.ccodfaconc = f.ccodfaconc
LEFT JOIN dbo.imfrefac frec    ON frec.ccodfrefac = pol.ccodfrefac
WHERE f.dfechfact BETWEEN :fecha_desde AND :fecha_hasta
ORDER BY cli.inumclient, f.dfechfact;
```

(Los campos ESTIMADO y los 14 de roles van en sub-selects/lógica aparte, como se describió arriba — no los metí en el SELECT principal para no complicar el query base.)

## Requisitos técnicos

- Usa el ORM/driver que ya tenga el proyecto (SQLAlchemy + `pyodbc`/`pymssql`, lo que ya esté configurado).
- Si algún join requiere un modelo que no existe aún, créalo siguiendo el patrón de los modelos existentes del proyecto (mismo estilo de nombres de clase/tabla).
- Maneja collation: esta base mezcla `Latin1_General_CI_AS` y otras collations en algunas columnas varchar/nvarchar comparadas entre tablas distintas; si el ORM genera comparaciones de texto entre columnas de distintas tablas y SQL Server tira error de "collation conflict", aplica `COLLATE DATABASE_DEFAULT` en esa comparación específica (visto en: comparaciones con `t_creditos.numpoliza`/`numfactura`).
- Devuelve 500 con mensaje genérico si falla la query, pero loguea el error completo server-side (no exponer detalles de la DB al cliente del API).
- Documenta el endpoint en el esquema de OpenAPI/Swagger existente del proyecto (parámetros, ejemplo de respuesta, y nota sobre los 4 campos ESTIMADO).

## Qué NO hacer todavía

No optimices ni cambies la fórmula de los 4 campos ESTIMADO — eso lo resolvemos después en una iteración separada, una vez validemos los montos reales con el equipo de cobros. Por ahora solo necesito que el endpoint funcione end-to-end con lo que ya está verificado, y que los 4 campos estimados vengan con su valor actual (aunque no sea 100% exacto) para no bloquear el resto del desarrollo.
