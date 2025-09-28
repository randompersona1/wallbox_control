import logging
import threading
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from wallbox_control.main import WallboxController
from pydantic import BaseModel


class MaxCurrentRequest(BaseModel):
    """Request model for setting maximum current."""

    max_current: float

    class Config:
        json_schema_extra = {"example": {"max_current": 16.0}}


class WebServerController:
    """
    FastAPI web server controller for wallbox management.

    Provides REST API endpoints to:
    - GET /status: Get all wallbox properties as JSON
    - POST /max_current: Set the maximum charging current
    """

    def __init__(
        self,
        wallbox_controller: WallboxController,
        host: str = "0.0.0.0",
        port: int = 8000,
    ):
        """
        Initialize the web server controller.

        Args:
            wallbox_controller: Thread-safe wallbox controller instance
            host: Host address to bind the server to (default: 0.0.0.0)
            port: Port number to run the server on (default: 8000)
        """
        self.wallbox_controller = wallbox_controller
        self.host = host
        self.port = port
        self.app = FastAPI(
            title="Wallbox Control API",
            description="REST API for controlling wallbox charging parameters",
            version="1.0.0",
        )
        self._server_thread: threading.Thread | None = None
        self._running = False

        # Configure logging
        self.logger = logging.getLogger(__name__)

        # Setup routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.get("/status", response_model=dict[str, Any])
        async def get_wallbox_status():
            """
            Get all current wallbox settings and status information.

            Returns a dictionary containing all readable wallbox properties
            including voltages, currents, charging state, temperatures, etc.
            """
            try:
                return self.wallbox_controller.get_all_properties()
            except Exception as e:
                self.logger.error("Failed to get wallbox status: %s", e)
                raise HTTPException(
                    status_code=500, detail=f"Failed to get wallbox status: {str(e)}"
                ) from e

        @self.app.post("/max_current")
        async def set_max_current(request: MaxCurrentRequest):
            """
            Set the maximum charging current for the wallbox.

            Args:
                request: Request containing the new maximum current value in Amperes

            Returns:
                Success message with the set current value
            """
            try:
                # Validate current range (basic validation, wallbox may have its own limits)
                if request.max_current < 0:
                    raise HTTPException(
                        status_code=400, detail="Maximum current cannot be negative"
                    )

                if request.max_current > 63:  # Typical maximum for most wallboxes
                    raise HTTPException(
                        status_code=400,
                        detail="Maximum current exceeds safe limit (63A)",
                    )

                # Set the current
                success = self.wallbox_controller.set_max_current(request.max_current)

                if not success:
                    raise HTTPException(
                        status_code=500, detail="Failed to set maximum current"
                    )

                self.logger.info(
                    "Maximum current set to %.1fA via API", request.max_current
                )

                return {
                    "message": f"Maximum current successfully set to {request.max_current}A",
                    "max_current": request.max_current,
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("Failed to set max current: %s", e)
                raise HTTPException(
                    status_code=500, detail=f"Failed to set max current: {str(e)}"
                ) from e

        @self.app.get("/")
        async def root():
            """Root endpoint with basic API information."""
            return {
                "message": "Wallbox Control API",
                "version": "1.0.0",
                "endpoints": {
                    "GET /status": "Get current wallbox status and settings",
                    "POST /max_current": "Set maximum charging current",
                    "GET /docs": "Interactive API documentation",
                },
            }

    def start(self):
        """Start the web server in a background thread."""
        if self._running:
            self.logger.warning("Web server is already running")
            return

        self._running = True

        def run_server():
            """Run the uvicorn server."""
            try:
                uvicorn.run(
                    self.app,
                    host=self.host,
                    port=self.port,
                    log_level="info",
                    access_log=True,
                )
            except Exception as e:
                self.logger.error("Web server failed: %s", e)
            finally:
                self._running = False

        self._server_thread = threading.Thread(
            target=run_server, daemon=True, name="WebServer"
        )
        self._server_thread.start()

        self.logger.info("Web server started on http://%s:%d", self.host, self.port)
        self.logger.info(
            "API documentation available at http://%s:%d/docs", self.host, self.port
        )

    def stop(self):
        """Stop the web server."""
        if not self._running:
            return

        self._running = False

        # Note: uvicorn doesn't have a clean way to stop from another thread
        # In a production environment, you'd want to use uvicorn's programmatic API
        # or implement a proper shutdown mechanism

        if self._server_thread and self._server_thread.is_alive():
            self.logger.info("Web server stop requested")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


def web_server_worker(
    wallbox_controller: WallboxController, host: str = "0.0.0.0", port: int = 8000
):
    """
    Worker function to start the web server.

    This function can be run in a thread similar to the GPIO worker.

    Args:
        wallbox_controller: Thread-safe wallbox controller instance
        host: Host address to bind the server to (default: 0.0.0.0)
        port: Port number to run the server on (default: 8000)
    """
    server = WebServerController(wallbox_controller, host, port)
    server.start()

    # Keep the thread alive
    try:
        while server._running:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        server.stop()
