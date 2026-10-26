# Prompt para el proyecto de la API (pegar tal cual)

---

Necesito implementar un endpoint en nuestra API interna que exponga el "Reporte de Comisiones Generadas Asociadas a Pólizas - Recibo Multi Vendor" del sistema de corretaje de seguros (base de datos SQL Server `SIAsegCaceres`). Ya reconstruí y validé el query SQL necesario contra la base real (incluyendo una corrección de un bug de filtro de fechas); tu trabajo es implementarlo como endpoint, reusando los modelos que ya tengo registrados y creando los que falten.

## Contexto del negocio

Reporte de comisiones generadas/liquidadas por recibo, usado por el área de cobros/comisiones. Grano: **una fila por recibo-póliza (`imrecpol`) × coaseguradora (`imfactcoaseg`)**. El nombre "Multi Vendor" se refiere a pólizas coaseguradas por varias aseguradoras ("vendors"): si una factura tiene 2+ coaseguradoras registradas, el recibo se repite una vez por cada una, cada una con su propio `% Part.`. Si la factura no tiene coaseguro explícito, se genera 1 sola fila con la aseguradora líder de la póliza al 100%.

## Modelos / tablas involucradas

Reutiliza los modelos que ya tengo para estas tablas si existen (varias ya se usaron en el endpoint de "Reporte de Producción"); si no, créalos (todas en el schema `dbo` de SQL Server):

- `imrecpol` (aplicación de recibo a factura/póliza) — grano base del reporte
- `imrecibo` (recibos) — join por `ccodrecibo`
- `imfact` (facturas) — join por `ccodfact`
- `impoliza` (pólizas) — join por `ccodpoliza`
- `imclient` (clientes) — join por `ccodclien`; auto-join adicional por `ccodgrupo` (cliente padre, para "Grupo Deudor")
- `imclientdet` (detalle cliente) — join por `ccodclien`, da sucursal y tipo de cliente
- `imsucursal` (catálogo sucursales)
- `imtipclient` (catálogo tipo de cliente)
- `imsubram` (subramo) — join por `ccodsubram` desde `impoliza`
- `imramos` (catálogo de ramos) — join por `ccodramo` desde `imsubram`
- `imareram` (mapeo subramo→área) — join por `ccodsubram`
- `imarea` (catálogo de áreas) — join por `ccodarea`
- `imciaseg` (aseguradoras) — join por `ccodciaseg`, se usa **dos veces** (aseguradora líder de la póliza y aseguradora/coaseguradora del recibo)
- `imfactcoaseg` (coaseguro declarado a nivel de factura) — join por `ccodfact`; base de la expansión "Multi Vendor"
- `imfaconc` (catálogo de conceptos) — se usa **dos veces**: concepto de la factura (`imfact.ccodfaconc`) y concepto del recibo (`imrecibo.ccodfaconc`)
- `imfrmpag` (catálogo de formas de pago) — join por `ccodfrmpag` desde `imrecibo`
- `imrecing` (recibos de ingreso de comisión) — join vía `imrecpol.ccodrecing`
- `imcocorretaje` (asignación de corredor por póliza, con `% Part.`) — join por `ccodpoliza`
- `cocorredores` (catálogo de corredores/brokers) — join por `ccodcorredor`

## Endpoint a crear

```
GET /api/reportes/comisiones-recibo-multivendor?fecha_desde=YYYY-MM-DD&fecha_hasta=YYYY-MM-DD&cliente=<texto opcional>
```

- `fecha_desde` y `fecha_hasta`: requeridos. Filtran por `imrecibo.dfechrecibo` **o** `imfact.dfechcierreprod` (el reporte original no deja claro cuál de los dos usa con certeza; se dejaron ambos con OR para no perder filas — ver nota de riesgo más abajo).
- `cliente`: opcional, string. Filtra por coincidencia parcial (`LIKE '%texto%'`) contra `imclient.cnomcliente`, sin distinguir mayúsculas/minúsculas.
- Validar que `fecha_desde <= fecha_hasta`; si no, 400 con mensaje claro.
- **Importante sobre fechas**: `fecha_desde`/`fecha_hasta` deben tratarse como **rango de días completos**, no como instantes. `imrecibo.dfechrecibo` trae hora (ej. `2026-09-30 14:31:47`), así que el filtro debe ser `dfechrecibo >= fecha_desde AND dfechrecibo < fecha_hasta + 1 día` — **nunca** un `BETWEEN` con ambos límites como fecha pura sin hora, porque eso trunca el día `fecha_hasta` a medianoche exacta y descarta casi todos los recibos de ese día (bug real que encontré y corregí validándolo contra la base).
- Respuesta: JSON con `{"total": <int>, "filtros": {...}, "data": [ {...fila...}, ... ]}`.
- Pagina si el volumen es grande (sugerido: `limit`/`offset` opcionales).

## Campos de cada fila (nombres snake_case para el JSON)

```
cod_cliente, cliente, grupo_deudor, sucursal, tipo_cliente, fecha_cliente, area, ramo,
fecha_emision, poliza, aseguradora, coaseguro, porcentaje_participacion, moneda,
recibo, concepto_recibo, forma_pago, fecha_recibo, fecha_registro, factura,
inicio_vig_factura, dias, concepto, gastos_admin, prima_bruta, prima_neta,
mantiene_porcentaje_comis, recibo_comisiones, porcentaje_comis, comision_generada,
comision_liquidada, diferencia, porcentaje_sobrecomis, sobrecomis_generada,
sobrecomis_liquidada, sobrecomis_diferencia, agente_poliza, porcentaje_incentivo_agente
```

## Lógica de cada campo

- `cod_cliente` = `imclient.inumclient`
- `cliente` = `imclient.cnomcliente`
- `grupo_deudor` = nombre del cliente apuntado por `imclient.ccodgrupo` (self-join); si es nulo o no tiene match, usar el propio nombre del cliente
- `sucursal` = `imclientdet.ccodsucursal` → `imsucursal.cdescripcion`
- `tipo_cliente` = `imclientdet.imtipclientid` → `imtipclient.tipo`
- `fecha_cliente` = `imclient.dfechingreso`
- `area` = `impoliza.ccodsubram` → `imareram.ccodarea` → `imarea.cdescripcion`
- `ramo` = `impoliza.ccodsubram` → `imsubram.ccodramo` → `imramos.cdescripcion`
- `fecha_emision` = `impoliza.dfechemis`
- `poliza` = `impoliza.cnumpoliza`
- `aseguradora` = `impoliza.ccodciaseg` → `imciaseg.cnombre` (aseguradora líder de la póliza)
- `coaseguro` / `porcentaje_participacion` = de `imfactcoaseg` (filtrado por `ccodfact` de la fila); si la factura no tiene fila en `imfactcoaseg`, usar la aseguradora líder de la póliza al 100% como única fila (ver "Lógica de expansión Multi Vendor" abajo)
- `moneda` = `impoliza.cmoneda`
- `recibo` = `imrecibo.cnumrecprov` (**verificado exacto contra dato real**: valor `"4002143-4685440"`)
- `concepto_recibo` = `imrecibo.ccodfaconc` → `imfaconc.cdescripcion`
- `forma_pago` = `imrecibo.ccodfrmpag` → `imfrmpag.cdescripcion`
- `fecha_recibo` = `imrecibo.dfechrecibo`
- `fecha_registro` = `imrecibo.tfechregistro`
- `factura` = `imfact.cnumfact`
- `inicio_vig_factura` = `imfact.dinivigen`
- `dias` = `DATEDIFF(día, imfact.dinivigen, imrecibo.dfechrecibo)` (**verificado exacto**: -1 y 14 en los 2 casos de prueba)
- `concepto` = `imfact.ccodfaconc` → `imfaconc.cdescripcion` (concepto de la FACTURA, no confundir con `concepto_recibo`)
- `gastos_admin` = `imfact.ygadministrativo`
- `prima_bruta` = `imfact.yprimabruta`
- `prima_neta` = `imfact.yprimaneta`
- `mantiene_porcentaje_comis` = `impoliza.mantenerporcomis` (bit) → `"Si"` / `""`
- `recibo_comisiones` = `imrecpol.ccodrecing` → `imrecing.inumrecing` (**verificado**: viene `null` cuando `ccodrecing` es `NULL`, que es el caso normal de comisión aún no liquidada)
- `porcentaje_comis` = `imrecpol.bporcomis`
- `comision_generada` = `ROUND(imrecpol.yaplicado * imrecpol.bporcomis / 100, 2)` (**verificado exacto** contra 2 casos reales)
- `comision_liquidada` = `imrecpol.ycomisrecibida`
- `diferencia` = `comision_generada - comision_liquidada`
- `porcentaje_sobrecomis` = `imrecpol.ysobrecomision`
- `sobrecomis_generada` = `ROUND(imrecpol.yaplicado * imrecpol.ysobrecomision / 100, 2)` (**verificado exacto**)
- `sobrecomis_diferencia` = `sobrecomis_generada - sobrecomis_liquidada`
- `agente_poliza` / `porcentaje_incentivo_agente` — ver sección de **campo ESTIMADO** abajo, es el único punto flojo del reporte.

### Lógica de expansión "Multi Vendor" (coaseguro)

Para cada factura:
1. Si existen filas en `imfactcoaseg` con ese `ccodfact`, generar una fila del reporte por cada una, usando su `ccodciaseg` (→ nombre en `imciaseg`) como `coaseguro` y su `nporcpart` como `porcentaje_participacion`.
2. Si no existen filas en `imfactcoaseg` para esa factura, generar **una sola fila** usando la aseguradora líder de la póliza (`impoliza.ccodciaseg`) como `coaseguro`, con `porcentaje_participacion = 100`.

(Esto fue validado estructuralmente — un caso real sin coaseguro se comportó como el punto 2 — pero **no se pudo probar el punto 1 con un caso real de coaseguro múltiple**, porque no había ninguno disponible en los datos de prueba. Revisar con un caso real antes de dar por cerrado el comportamiento con 2+ coaseguradoras.)

## Campo ESTIMADO/INCIERTO — IMPORTANTE, no está validado

**`agente_poliza` y `porcentaje_incentivo_agente`** son el único punto débil real del reporte:

- `impoliza.cagenteid` no tiene FK declarada en el esquema (no hay forma estructural de saber a qué tabla apunta).
- Se descartó mapear a `imejecut` (la tabla de empleados usada para los roles del otro reporte de producción) porque el valor real observado es `"CACERES & ASOCIADOS"`, un nombre de empresa, no de persona.
- Se probó mapear a `dbo.cocorredores` (catálogo de corredores) vía `dbo.imcocorretaje` (asignación de corredor por póliza) — pero **`cocorredores` está completamente vacía** en el ambiente donde validé esto, así que no se pudo confirmar.
- Existe una vista real `dbo.vw_Comis_Generada` (construida sobre una tabla de staging `dbo.ST_ProPago`) que trae una columna `Agente` ya resuelta por la aplicación/ETL — con alta probabilidad esa es la fuente real que usa el reporte original. Pero **`ST_ProPago` también está vacía** en el ambiente donde probé, así que tampoco se pudo leer el valor real desde ahí.

Implementa por ahora con el fallback a `cocorredores`/`imcocorretaje` (fórmula abajo), pero:
- Agrega en la respuesta un campo `advertencias: ["agente_poliza y porcentaje_incentivo_agente no están validados contra un caso real; revisar si el ambiente de producción tiene datos en ST_ProPago / vw_Comis_Generada.Agente para resolverlo de forma definitiva"]`.
- Deja un TODO/hook claro en el código para poder cambiar la fuente de este campo sin tocar el resto del endpoint — lo ideal a futuro es reemplazarlo por un `SELECT Agente FROM dbo.vw_Comis_Generada WHERE ...` si esa vista resulta tener datos reales en producción.

Fórmula actual (mejor esfuerzo, no exacta):

```sql
agente_poliza = ISNULL(
    (SELECT TOP 1 cor.cnombre FROM imcocorretaje ic JOIN cocorredores cor ON cor.ccodcorredor = ic.ccodcorredor
     WHERE ic.ccodpoliza = <poliza de la fila> ORDER BY ic.nporcpart DESC),
    (SELECT TOP 1 cor2.cnombre FROM cocorredores cor2 WHERE cor2.cdefault = 1)
)
porcentaje_incentivo_agente = ISNULL(
    (SELECT TOP 1 ic.nporcpart FROM imcocorretaje ic WHERE ic.ccodpoliza = <poliza de la fila> ORDER BY ic.nporcpart DESC),
    0
)
```

## Query SQL de referencia (ya probado contra la base real, corre sin errores y devuelve el resultado esperado)

```sql
DECLARE @FechaDesde DATETIME = '2026-09-30';
DECLARE @FechaHasta DATETIME = '2026-09-30';
DECLARE @Cliente    NVARCHAR(200) = NULL;   -- filtro opcional, nombre parcial del cliente

;WITH Coaseg AS (
    SELECT fc.ccodfact, fc.ccodciaseg, fc.nporcpart
    FROM dbo.imfactcoaseg fc
    UNION ALL
    SELECT f2.ccodfact, pol2.ccodciaseg, CAST(100.00 AS numeric(18,2))
    FROM dbo.imfact f2
    JOIN dbo.impoliza pol2 ON pol2.ccodpoliza = f2.ccodpoliza
    WHERE NOT EXISTS (SELECT 1 FROM dbo.imfactcoaseg fc2 WHERE fc2.ccodfact = f2.ccodfact)
)
SELECT
    cli.inumclient                                       AS cod_cliente,
    cli.cnomcliente                                       AS cliente,
    ISNULL(g.cnomcliente, cli.cnomcliente)                AS grupo_deudor,
    suc.cdescripcion                                      AS sucursal,
    tc.tipo                                               AS tipo_cliente,
    cli.dfechingreso                                      AS fecha_cliente,
    area.cdescripcion                                     AS area,
    ramo.cdescripcion                                     AS ramo,
    pol.dfechemis                                         AS fecha_emision,
    pol.cnumpoliza                                        AS poliza,
    aseg.cnombre                                          AS aseguradora,
    caseg.cnombre                                         AS coaseguro,
    cs.nporcpart                                          AS porcentaje_participacion,
    pol.cmoneda                                           AS moneda,
    r.cnumrecprov                                         AS recibo,
    rconc.cdescripcion                                    AS concepto_recibo,
    frmpag.cdescripcion                                   AS forma_pago,
    r.dfechrecibo                                         AS fecha_recibo,
    r.tfechregistro                                       AS fecha_registro,
    f.cnumfact                                            AS factura,
    f.dinivigen                                           AS inicio_vig_factura,
    DATEDIFF(DAY, f.dinivigen, r.dfechrecibo)             AS dias,
    conc.cdescripcion                                     AS concepto,
    f.ygadministrativo                                    AS gastos_admin,
    f.yprimabruta                                         AS prima_bruta,
    f.yprimaneta                                          AS prima_neta,
    (CASE WHEN pol.mantenerporcomis = 1 THEN 'Si' ELSE '' END) AS mantiene_porcentaje_comis,
    (SELECT TOP 1 ri.inumrecing FROM dbo.imrecing ri WHERE ri.ccodrecing = rp.ccodrecing)
                                                           AS recibo_comisiones,
    rp.bporcomis                                          AS porcentaje_comis,
    ROUND(rp.yaplicado * rp.bporcomis / 100.0, 2)         AS comision_generada,
    rp.ycomisrecibida                                     AS comision_liquidada,
    ROUND(rp.yaplicado * rp.bporcomis / 100.0, 2) - rp.ycomisrecibida
                                                           AS diferencia,
    rp.ysobrecomision                                     AS porcentaje_sobrecomis,
    ROUND(rp.yaplicado * rp.ysobrecomision / 100.0, 2)    AS sobrecomis_generada,
    (CASE WHEN rp.bporcomis <> 0
          THEN rp.ycomisrecibida * (rp.ysobrecomision / rp.bporcomis)
          ELSE rp.yaplicado * (pol.ysobrecomision / 100.0)
     END)                                                 AS sobrecomis_liquidada,
    (ROUND(rp.yaplicado * rp.ysobrecomision / 100.0, 2)
     - (CASE WHEN rp.bporcomis <> 0
             THEN rp.ycomisrecibida * (rp.ysobrecomision / rp.bporcomis)
             ELSE rp.yaplicado * (pol.ysobrecomision / 100.0)
        END))                                             AS sobrecomis_diferencia,
    ISNULL(
      (SELECT TOP 1 cor.cnombre FROM dbo.imcocorretaje ic
       JOIN dbo.cocorredores cor ON cor.ccodcorredor = ic.ccodcorredor
       WHERE ic.ccodpoliza = pol.ccodpoliza ORDER BY ic.nporcpart DESC),
      (SELECT TOP 1 cor2.cnombre FROM dbo.cocorredores cor2 WHERE cor2.cdefault = 1)
    )                                                      AS agente_poliza,
    ISNULL(
      (SELECT TOP 1 ic.nporcpart FROM dbo.imcocorretaje ic
       WHERE ic.ccodpoliza = pol.ccodpoliza ORDER BY ic.nporcpart DESC),
      0)                                                   AS porcentaje_incentivo_agente
FROM dbo.imrecpol rp
JOIN dbo.imrecibo r           ON r.ccodrecibo   = rp.ccodrecibo
JOIN dbo.imfact f             ON f.ccodfact     = rp.ccodfact
JOIN dbo.impoliza pol         ON pol.ccodpoliza = f.ccodpoliza
JOIN Coaseg cs                ON cs.ccodfact    = f.ccodfact
JOIN dbo.imciaseg caseg       ON caseg.ccodciaseg = cs.ccodciaseg
JOIN dbo.imciaseg aseg        ON aseg.ccodciaseg  = pol.ccodciaseg
JOIN dbo.imclient cli         ON cli.ccodclien    = pol.ccodclien
LEFT JOIN dbo.imclient g      ON g.ccodclien      = cli.ccodgrupo
LEFT JOIN dbo.imclientdet cdet ON cdet.ccodclien  = cli.ccodclien
LEFT JOIN dbo.imsucursal suc   ON suc.ccodsucursal = cdet.ccodsucursal
LEFT JOIN dbo.imtipclient tc   ON tc.imtipclientid = cdet.imtipclientid
JOIN dbo.imsubram sub         ON sub.ccodsubram   = pol.ccodsubram
JOIN dbo.imramos ramo         ON ramo.ccodramo    = sub.ccodramo
LEFT JOIN dbo.imareram ar     ON ar.ccodsubram    = sub.ccodsubram
LEFT JOIN dbo.imarea area      ON area.ccodarea    = ar.ccodarea
LEFT JOIN dbo.imfaconc conc    ON conc.ccodfaconc  = f.ccodfaconc
LEFT JOIN dbo.imfaconc rconc   ON rconc.ccodfaconc = r.ccodfaconc
LEFT JOIN dbo.imfrmpag frmpag  ON frmpag.ccodfrmpag = r.ccodfrmpag
WHERE r.lanulado = 0
  AND (r.dfechrecibo >= @FechaDesde AND r.dfechrecibo < DATEADD(DAY, 1, @FechaHasta)
       OR f.dfechcierreprod >= @FechaDesde AND f.dfechcierreprod < DATEADD(DAY, 1, @FechaHasta))
  AND (@Cliente IS NULL OR cli.cnomcliente LIKE '%' + @Cliente + '%')
ORDER BY cli.inumclient, r.dfechrecibo, f.cnumfact;
```

## Requisitos técnicos

- Usa el ORM/driver que ya tenga el proyecto (SQLAlchemy + `pyodbc`/`pymssql`, lo que ya esté configurado), igual que en el endpoint de "Reporte de Producción".
- Si algún join requiere un modelo que no existe aún, créalo siguiendo el patrón de los modelos existentes del proyecto.
- Maneja collation: esta base mezcla `Latin1_General_CI_AS` y otras collations en algunas columnas varchar/nvarchar comparadas entre tablas distintas (ya visto en el endpoint de producción con `t_creditos`); si el ORM genera comparaciones de texto entre columnas de distintas tablas y SQL Server tira error de "collation conflict", aplica `COLLATE DATABASE_DEFAULT` en esa comparación específica.
- `r.lanulado = 0` siempre debe aplicarse (excluir recibos anulados).
- Devuelve 500 con mensaje genérico si falla la query, pero loguea el error completo server-side.
- Documenta el endpoint en el esquema de OpenAPI/Swagger existente del proyecto (parámetros, ejemplo de respuesta, y nota sobre el campo `agente_poliza`/`porcentaje_incentivo_agente` no validado).

## Qué NO hacer todavía

No optimices ni cambies la fórmula de `agente_poliza`/`porcentaje_incentivo_agente` — eso se resuelve después, cuando se confirme si `ST_ProPago`/`vw_Comis_Generada` tienen datos reales en el ambiente de producción. Por ahora solo necesito que el endpoint funcione end-to-end con lo ya verificado (que es la gran mayoría del reporte), y que ese campo venga con su valor actual (aunque no sea 100% exacto) para no bloquear el resto del desarrollo. Tampoco optimices todavía el caso de coaseguro múltiple real (2+ aseguradoras) más allá de lo ya descrito — probarlo con un caso real es trabajo de una iteración futura.
