import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.ai.errors import AIAdapterError, ProviderTimeoutError


class AppError(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PermissionDenied(AppError):
    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message, status.HTTP_403_FORBIDDEN)


class ApprovalRequired(AppError):
    def __init__(self, approval_id: str, message: str = "Approval required") -> None:
        self.approval_id = approval_id
        super().__init__(message, status.HTTP_409_CONFLICT)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AIAdapterError)
    async def ai_adapter_error_handler(_: Request, exc: AIAdapterError) -> JSONResponse:
        status_code = (status.HTTP_504_GATEWAY_TIMEOUT
                       if isinstance(exc, ProviderTimeoutError)
                       else status.HTTP_503_SERVICE_UNAVAILABLE)
        return JSONResponse(
            status_code=status_code,
            content={"error": {"message": exc.message, "type": exc.__class__.__name__}},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        content = {"error": {"message": exc.message, "type": exc.__class__.__name__}}
        if isinstance(exc, ApprovalRequired):
            content["error"]["approval_id"] = exc.approval_id
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
        raw_details = exc.errors() if isinstance(
            exc, (ValidationError, RequestValidationError)
        ) else []
        details = [{key: value for key, value in detail.items()
                    if key in {"type", "loc", "msg"}} for detail in raw_details]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"message": "Validation failed", "details": details}},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        structlog.get_logger("api").exception(
            "unhandled_request_error",
            path=request.url.path,
            method=request.method,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"message": "Internal server error", "type": "InternalError"}},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        structlog.get_logger("database").warning(
            "integrity_constraint_rejected", error_type=type(exc.orig).__name__
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"message": "Resource conflicts with existing data"}},
        )
