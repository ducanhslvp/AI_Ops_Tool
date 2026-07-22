from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query, Response
from pydantic import BaseModel, ConfigDict


class ApiMessage(BaseModel):
    message: str


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Timestamped(OrmModel):
    id: str
    created_at: datetime
    updated_at: datetime


class Pagination:
    """Page contract with backward-compatible offset/limit support."""

    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        offset: int | None = Query(None, ge=0),
        limit: int | None = Query(None, ge=1, le=500),
    ) -> None:
        self.page = page
        self.page_size = limit or page_size
        self.offset = offset if offset is not None else (page - 1) * page_size


PaginationDep = Annotated[Pagination, Depends()]


def set_pagination_headers(response: Response, total: int, pagination: Pagination) -> None:
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(pagination.page)
    response.headers["X-Page-Size"] = str(pagination.page_size)
