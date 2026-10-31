from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, require_admin
from app.core.permissions import is_staff
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.plan import PlanCreate, PlanResponse, PlanUpdate
from app.services import plan_service

router = APIRouter()


@router.get("", response_model=Page[PlanResponse])
def list_plans(
    search: str | None = Query(None),
    is_active: bool | None = Query(None, description="Staff only; ignored for customers"),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    staff = is_staff(current_user)
    items, total = plan_service.list_plans(
        db, params.offset, params.page_size, staff, search, is_active
    )
    return Page(
        items=[PlanResponse.from_plan(p, staff) for p in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    staff = is_staff(current_user)
    return PlanResponse.from_plan(plan_service.get_plan(db, plan_id, staff), staff)


@router.post("", response_model=PlanResponse, status_code=201)
def create_plan(
    payload: PlanCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    return PlanResponse.from_plan(plan_service.create_plan(db, payload), True)


@router.put("/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return PlanResponse.from_plan(plan_service.update_plan(db, plan_id, payload), True)


@router.delete("/{plan_id}", status_code=204)
def deactivate_plan(
    plan_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    plan_service.deactivate_plan(db, plan_id)