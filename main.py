from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import traceback
from datetime import datetime
from controllers import imclient_controller, impoliza_controller, client_controller, kyc_controller, logs_controller

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api_errors.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

tags_metadata = [
    {
        "name": "Clientes",
        "description": "Consulta de clientes de la tabla imclient con todos sus campos.",
    },
    {
        "name": "Polizas",
        "description": "Consulta de pólizas de la tabla impoliza con todos sus campos. "
                       "Una póliza activa es la que tiene ccodpolsta = '00000001'.",
    },
]

app = FastAPI(
    title="API SIA Seguros - Clientes",
    description="API para consultar información de clientes desde SQL Server",
    version="1.0.0",
    openapi_tags=tags_metadata
)

app.include_router(imclient_controller.router)
app.include_router(impoliza_controller.router)
app.include_router(client_controller.router)
app.include_router(kyc_controller.router)
app.include_router(logs_controller.router)

# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Mantiene el status_code original de HTTPException (401/403/404/etc).
    """
    logger.warning(
        f"HTTPException en {request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "status_code": exc.status_code,
            "detail": str(exc.detail),
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "timestamp": datetime.now().isoformat(),
        },
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Manejador global de excepciones para capturar todos los errores no manejados
    """
    logger.error(
        f"Error no manejado en {request.method} {request.url.path}",
        exc_info=True,
        extra={
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc()
        }
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Error interno del servidor",
            "detail": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )


@app.get("/")
async def root():
    """
    Endpoint raíz de la API
    """
    return {
        "message": "API SIA Seguros - Clientes",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
