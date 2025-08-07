"""
Run the COA Backend API with HTTPS support
"""
import os
import sys
import uvicorn
from app.config import settings

def main():
    """Run the application"""
    # Check if SSL certificates exist
    ssl_enabled = settings.SSL_ENABLED

    if ssl_enabled:
        if not os.path.exists(settings.SSL_CERTFILE) or not os.path.exists(settings.SSL_KEYFILE):
            print(f"Warning: SSL certificates not found at {settings.SSL_CERTFILE} and {settings.SSL_KEYFILE}")
            print("Running in HTTP mode. To enable HTTPS:")
            print("1. Copy your certificate files to the certs/ directory")
            print("2. Or set SSL_ENABLED=False in .env file")
            ssl_enabled = False

    # Configure uvicorn
    config_args = {
        "app": "app.main:app",
        "host": settings.HOST,
        "port": settings.PORT,
        "reload": settings.DEBUG,
        "root_path": "/api/aimta"
    }

    if ssl_enabled:
        config_args.update({
            "ssl_keyfile": settings.SSL_KEYFILE,
            "ssl_certfile": settings.SSL_CERTFILE,
        })
        print(f"Starting HTTPS server on https://{settings.HOST}:{settings.PORT}")
    else:
        print(f"Starting HTTP server on http://{settings.HOST}:{settings.PORT}")

    # Run the server
    uvicorn.run(**config_args)


if __name__ == "__main__":
    main()
