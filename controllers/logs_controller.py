from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Optional
from math import ceil
import logging
import os
import re
from auth import verify_credentials

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/logs", response_class=JSONResponse)
async def get_logs(
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(50, ge=1, le=500, description="Tamaño de página"),
    level: Optional[str] = Query(None, description="Filtro por nivel (ERROR, WARNING, INFO)"),
    endpoint: Optional[str] = Query(None, description="Filtro por endpoint"),
    username: str = Depends(verify_credentials)
):
    """
    Obtiene los logs de la API con paginación y filtros opcionales.
    """
    log_file = "api_errors.log"
    
    if not os.path.exists(log_file):
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "data": []
        }
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Parsear logs
        log_entries = []
        current_entry = {}
        
        for line in lines:
            # Patrón para detectar inicio de nueva entrada de log
            # Formato: YYYY-MM-DD HH:MM:SS,mmm - nombre - LEVEL - mensaje
            log_pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\S+) - (\w+) - (.+)$'
            match = re.match(log_pattern, line.strip())
            
            if match:
                if current_entry:
                    log_entries.append(current_entry)
                timestamp, logger_name, level_name, message = match.groups()
                current_entry = {
                    "timestamp": timestamp,
                    "logger": logger_name,
                    "level": level_name,
                    "message": message,
                    "details": ""
                }
            else:
                # Continuación de la entrada anterior (traceback, etc.)
                if current_entry:
                    current_entry["details"] += line
        
        if current_entry:
            log_entries.append(current_entry)
        
        # Revertir para mostrar los más recientes primero
        log_entries.reverse()
        
        # Aplicar filtros
        filtered_entries = log_entries
        if level:
            filtered_entries = [e for e in filtered_entries if e["level"] == level.upper()]
        if endpoint:
            filtered_entries = [e for e in filtered_entries if endpoint.lower() in e["message"].lower()]
        
        # Paginación
        total = len(filtered_entries)
        total_pages = ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size
        paginated_entries = filtered_entries[offset:offset + page_size]
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": paginated_entries
        }
        
    except Exception as e:
        logger.error(f"Error al leer logs: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al leer los logs: {str(e)}"
        )


@router.get("/logs", response_class=HTMLResponse)
async def view_logs_html(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    level: Optional[str] = Query(None),
    endpoint: Optional[str] = Query(None),
    username: str = Depends(verify_credentials)
):
    """
    Interfaz visual HTML para ver los logs de la API.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Logs de la API - SIA Seguros</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px;
                min-height: 100vh;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .filters {
                padding: 20px;
                background: #f5f5f5;
                border-bottom: 2px solid #e0e0e0;
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                align-items: center;
            }
            .filters input, .filters select, .filters button {
                padding: 10px 15px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
            }
            .filters button {
                background: #667eea;
                color: white;
                border: none;
                cursor: pointer;
                transition: background 0.3s;
            }
            .filters button:hover {
                background: #5568d3;
            }
            .logs-container {
                padding: 20px;
                max-height: 70vh;
                overflow-y: auto;
            }
            .log-entry {
                margin-bottom: 15px;
                padding: 15px;
                border-radius: 5px;
                border-left: 4px solid #ddd;
                background: #f9f9f9;
                transition: transform 0.2s;
            }
            .log-entry:hover {
                transform: translateX(5px);
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .log-entry.ERROR {
                border-left-color: #e74c3c;
                background: #fee;
            }
            .log-entry.WARNING {
                border-left-color: #f39c12;
                background: #fff8e1;
            }
            .log-entry.INFO {
                border-left-color: #3498db;
                background: #e3f2fd;
            }
            .log-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
                flex-wrap: wrap;
                gap: 10px;
            }
            .log-level {
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 12px;
                text-transform: uppercase;
            }
            .log-level.ERROR {
                background: #e74c3c;
                color: white;
            }
            .log-level.WARNING {
                background: #f39c12;
                color: white;
            }
            .log-level.INFO {
                background: #3498db;
                color: white;
            }
            .log-timestamp {
                color: #666;
                font-size: 0.9em;
            }
            .log-message {
                color: #333;
                font-weight: 500;
                margin-bottom: 5px;
            }
            .log-details {
                color: #666;
                font-size: 0.85em;
                font-family: 'Courier New', monospace;
                white-space: pre-wrap;
                background: #f5f5f5;
                padding: 10px;
                border-radius: 3px;
                margin-top: 10px;
                max-height: 200px;
                overflow-y: auto;
            }
            .pagination {
                padding: 20px;
                text-align: center;
                background: #f5f5f5;
                border-top: 2px solid #e0e0e0;
            }
            .pagination button {
                padding: 10px 20px;
                margin: 0 5px;
                border: 1px solid #ddd;
                background: white;
                border-radius: 5px;
                cursor: pointer;
                transition: all 0.3s;
            }
            .pagination button:hover:not(:disabled) {
                background: #667eea;
                color: white;
                border-color: #667eea;
            }
            .pagination button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .pagination span {
                margin: 0 10px;
                color: #666;
            }
            .no-logs {
                text-align: center;
                padding: 40px;
                color: #999;
            }
            .refresh-btn {
                background: #27ae60 !important;
            }
            .refresh-btn:hover {
                background: #229954 !important;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📋 Logs de la API</h1>
                <p>Sistema de monitoreo de errores y eventos</p>
            </div>
            <div class="filters">
                <input type="text" id="endpointFilter" placeholder="Filtrar por endpoint..." value="">
                <select id="levelFilter">
                    <option value="">Todos los niveles</option>
                    <option value="ERROR">ERROR</option>
                    <option value="WARNING">WARNING</option>
                    <option value="INFO">INFO</option>
                </select>
                <input type="number" id="pageSize" placeholder="Registros por página" value="50" min="1" max="500">
                <button onclick="loadLogs(1)">🔍 Filtrar</button>
                <button class="refresh-btn" onclick="loadLogs(currentPage)">🔄 Actualizar</button>
            </div>
            <div class="logs-container" id="logsContainer">
                <div class="no-logs">Cargando logs...</div>
            </div>
            <div class="pagination" id="pagination"></div>
        </div>
        <script>
            let currentPage = 1;
            let totalPages = 1;
            
            async function loadLogs(page = 1) {
                currentPage = page;
                const level = document.getElementById('levelFilter').value;
                const endpoint = document.getElementById('endpointFilter').value;
                const pageSize = document.getElementById('pageSize').value || 50;
                
                const params = new URLSearchParams({
                    page: page,
                    page_size: pageSize
                });
                if (level) params.append('level', level);
                if (endpoint) params.append('endpoint', endpoint);
                
                try {
                    const response = await fetch(`/api/logs?${params.toString()}`);
                    if (response.status === 401) {
                        document.getElementById('logsContainer').innerHTML =
                            '<div class="no-logs">Sesión no autorizada. Recarga la página e inicia sesión nuevamente.</div>';
                        return;
                    }
                    const data = await response.json();
                    
                    totalPages = data.total_pages;
                    displayLogs(data.data);
                    updatePagination(data.page, data.total_pages, data.total);
                } catch (error) {
                    document.getElementById('logsContainer').innerHTML = 
                        '<div class="no-logs">Error al cargar los logs: ' + error.message + '</div>';
                }
            }
            
            function displayLogs(logs) {
                const container = document.getElementById('logsContainer');
                
                if (logs.length === 0) {
                    container.innerHTML = '<div class="no-logs">No hay logs disponibles</div>';
                    return;
                }
                
                container.innerHTML = logs.map(log => `
                    <div class="log-entry ${log.level}">
                        <div class="log-header">
                            <span class="log-timestamp">${log.timestamp}</span>
                            <span class="log-level ${log.level}">${log.level}</span>
                        </div>
                        <div class="log-message">${escapeHtml(log.message)}</div>
                        ${log.details ? '<div class="log-details">' + escapeHtml(log.details) + '</div>' : ''}
                    </div>
                `).join('');
            }
            
            function updatePagination(page, totalPages, total) {
                const pagination = document.getElementById('pagination');
                pagination.innerHTML = `
                    <button onclick="loadLogs(${page - 1})" ${page === 1 ? 'disabled' : ''}>← Anterior</button>
                    <span>Página ${page} de ${totalPages} (Total: ${total} registros)</span>
                    <button onclick="loadLogs(${page + 1})" ${page === totalPages ? 'disabled' : ''}>Siguiente →</button>
                `;
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            // Cargar logs al iniciar
            loadLogs(1);
            
            // Auto-refresh cada 30 segundos
            setInterval(() => loadLogs(currentPage), 30000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
