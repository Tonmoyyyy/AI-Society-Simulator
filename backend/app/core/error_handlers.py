from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse


def register_error_handlers(app: FastAPI) -> None:
    """
    Central place for exception → response mapping, so every endpoint
    returns errors in the same { "error": { code, message } } shape.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # exc.errors() can contain non-JSON-native values (Decimal, bytes,
        # etc. from the rejected input) — jsonable_encoder converts those
        # before they hit the plain json.dumps inside JSONResponse. Without
        # this, any validation failure on a Decimal/Numeric field (e.g. a
        # negative wallet transfer amount) crashes with a 500 instead of
        # returning the intended 422.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": 422, "message": "Validation error", "details": jsonable_encoder(exc.errors())}},
        )
