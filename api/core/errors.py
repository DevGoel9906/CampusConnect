from fastapi import HTTPException, status


class AppError(HTTPException):
    pass


def not_found(resource: str = "Resource"):
    return HTTPException(status_code=404, detail=f"{resource} not found")


def unauthorized(msg: str = "Unauthorized"):
    return HTTPException(status_code=401, detail=msg)


def forbidden(msg: str = "Forbidden"):
    return HTTPException(status_code=403, detail=msg)


def conflict(msg: str):
    return HTTPException(status_code=409, detail=msg)


def bad_request(msg: str):
    return HTTPException(status_code=400, detail=msg)
