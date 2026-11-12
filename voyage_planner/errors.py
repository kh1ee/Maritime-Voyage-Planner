"""Error type that maps one-to-one onto API_SPECIFICATION.md section 8."""
from __future__ import annotations

from typing import Dict, List, Optional

# Minimum error codes required by the specification.
PORT_NOT_FOUND = "PORT_NOT_FOUND"
INVALID_COORDINATES = "INVALID_COORDINATES"
MISSING_ORIGIN = "MISSING_ORIGIN"
MISSING_DESTINATION = "MISSING_DESTINATION"
ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
INVALID_PASSAGE = "INVALID_PASSAGE"
INVALID_REQUEST = "INVALID_REQUEST"

ALL_ERROR_CODES = (
    PORT_NOT_FOUND, INVALID_COORDINATES, MISSING_ORIGIN, MISSING_DESTINATION,
    ROUTE_NOT_FOUND, INVALID_PASSAGE, INVALID_REQUEST,
)


class VoyagePlannerError(Exception):
    """Raised for any problem that the API must report as an error response."""

    def __init__(self, error_code: str, message: str,
                 warnings: Optional[List[str]] = None) -> None:
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code
        self.message = message
        self.warnings = list(warnings or [])

    def to_dict(self) -> Dict:
        """Exactly the shape shown in API_SPECIFICATION.md section 8."""
        return {
            "status": "error",
            "error_code": self.error_code,
            "message": self.message,
            "warnings": self.warnings,
        }
