"""CLI entrypoint to run the Job Review Dashboard server."""

import sys
import uvicorn
from app.config.settings import get_settings

def main() -> None:
    settings = get_settings()
    host = getattr(settings, "DASHBOARD_HOST", "127.0.0.1")
    port = getattr(settings, "DASHBOARD_PORT", 8000)

    print("==================================================")
    print("   Starting Job Review Dashboard                  ")
    print("==================================================")
    print(f"Server URL: http://{host}:{port}")
    print("Press CTRL+C to stop the dashboard server.")
    print("==================================================")

    uvicorn.run(
        "app.dashboard.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )

if __name__ == "__main__":
    main()
