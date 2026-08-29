"""
Punto de entrada: levanta el servidor web (mapa + streaming) en el puerto
configurado (9000) y arranca la simulación en segundo plano.

Uso:
    python main.py

El mapa queda disponible en http://127.0.0.1:9000
"""

import sys

import uvicorn

from config import ConfigurationError, load_settings

if __name__ == "__main__":
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        sys.exit(1)
    uvicorn.run("app:app", host=settings.web_host, port=settings.web_port, log_level="info")
