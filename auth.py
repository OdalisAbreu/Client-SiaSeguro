from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from config import ADMIN_USERNAME, ADMIN_PASSWORD
import secrets

security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Valida las credenciales del usuario
    """
    is_valid_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    is_valid_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    
    if not (is_valid_username and is_valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return credentials.username

