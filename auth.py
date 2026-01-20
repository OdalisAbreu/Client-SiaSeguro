from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from config import ADMIN_USERNAME, ADMIN_PASSWORD
import secrets
import logging

# Configurar logger para autenticación
logger = logging.getLogger(__name__)

security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Valida las credenciales del usuario
    """
    is_valid_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    is_valid_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    
    if not (is_valid_username and is_valid_password):
        logger.warning(
            f"Intento de autenticación fallido",
            extra={
                "username_provided": credentials.username,
                "username_valid": is_valid_username,
                "password_valid": is_valid_password,
                "ip_address": "N/A"  # Se puede agregar si se pasa el request
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return credentials.username

