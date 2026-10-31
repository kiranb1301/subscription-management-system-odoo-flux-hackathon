from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, require_admin, require_staff
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.quotation_template import TemplateCreate, TemplateResponse, TemplateUpdate
from app.services import quotation_template_service as service

router = APIRouter()


@router.get("", response_model=Page[TemplateResponse])
def list_templates(
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    items, total = service.list_templates(db, params.offset, params.page_size, search, is_active)
    return Page(
        items=[TemplateResponse.model_validate(t) for t in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)
):
    return service.get_template(db, template_id)


@router.post("", response_model=TemplateResponse, status_code=201)
def create_template(
    payload: TemplateCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    return service.create_template(db, payload)


@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return service.update_template(db, template_id, payload)


@router.delete("/{template_id}", status_code=204)
def deactivate_template(
    template_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    service.deactivate_template(db, template_id)