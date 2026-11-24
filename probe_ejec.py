import json, time, traceback
from datetime import date
from fastapi import HTTPException
out = {}
def dump():
    with open("_probe_out.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
try:
    import main
    from controllers import reporte_comisiones_recibo_controller as c
    d = date(2026, 9, 30)
    rutas = [getattr(r, "path", "") for r in main.app.routes]
    out["rutas"] = [p for p in rutas if "comisiones-recibo" in p]
    spec = main.app.openapi()
    def info(path):
        op = spec["paths"][path]["get"]
        params = [p["name"] for p in op.get("parameters", [])]
        ref = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
        resp = spec["components"]["schemas"][ref]
        row_ref = resp["properties"]["data"]["items"]["$ref"].split("/")[-1]
        row = spec["components"]["schemas"][row_ref]
        fil_ref = resp["properties"]["filtros"]["$ref"].split("/")[-1]
        fil = spec["components"]["schemas"][fil_ref]
        return {"summary": op.get("summary"), "params": params, "row_schema": row_ref,
                "row_has_analista": "analista_cobros_comisiones" in row["properties"],
                "filtros_has_analista": "analista" in fil["properties"],
                "example_has_analista": "analista" in json.dumps(op["responses"]["200"]["content"]["application/json"].get("example", {}))}
    out["openapi_sin"] = info("/api/reportes/comisiones-recibo-multivendor")
    out["openapi_con"] = info("/api/reportes/comisiones-recibo-multivendor-ejecutivo")
    for name, fn in [("sin", c.get_reporte_comisiones_recibo_multivendor), ("con", c.get_reporte_comisiones_recibo_multivendor_ejecutivo)]:
        try:
            fn(fecha_desde=date(2026, 10, 1), fecha_hasta=d, username="probe")
            out[f"400_{name}"] = "no error"
        except HTTPException as e:
            out[f"400_{name}"] = e.status_code
    dump()
    t = time.time(); rs = c.get_reporte_comisiones_recibo_multivendor(fecha_desde=d, fecha_hasta=d, username="probe"); out["t_sin"] = round(time.time() - t, 1)
    dump()
    t = time.time(); rc = c.get_reporte_comisiones_recibo_multivendor_ejecutivo(fecha_desde=d, fecha_hasta=d, username="probe"); out["t_con"] = round(time.time() - t, 1)
    ds = [r.model_dump(mode="json") for r in rs.data]
    dc = [r.model_dump(mode="json") for r in rc.data]
    out["total_sin"], out["total_con"], out["len_sin"], out["len_con"] = rs.total, rc.total, len(ds), len(dc)
    out["sin_filas_con_clave_analista"] = sum("analista_cobros_comisiones" in r for r in ds)
    out["sin_filtros_keys"] = list(rs.filtros.model_dump().keys())
    out["con_analista_no_nulo"] = sum(1 for r in dc if r.get("analista_cobros_comisiones"))
    out["filas_identicas"] = sum(1 for a, b in zip(ds, dc) if a == {k: v for k, v in b.items() if k != "analista_cobros_comisiones"})
    dump()
    t = time.time(); rm = c.get_reporte_comisiones_recibo_multivendor_ejecutivo(fecha_desde=d, fecha_hasta=d, analista="muñoz", username="probe"); out["t_munoz"] = round(time.time() - t, 1)
    out["total_munoz"], out["len_munoz"] = rm.total, len(rm.data)
    out["munoz_todos_coinciden"] = all("muñoz" in (r.analista_cobros_comisiones or "").lower() for r in rm.data)
    out["done"] = True
except Exception:
    out["error"] = traceback.format_exc()
dump()
