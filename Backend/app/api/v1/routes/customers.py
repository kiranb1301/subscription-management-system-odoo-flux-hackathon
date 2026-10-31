from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_customer, get_current_user, require_staff
from app.db.session import get_db
from app.models import Customer, User
from app.schemas.common import Page
from app.schemas.customer import CustomerResponse, CustomerSelfUpdate, CustomerStaffUpdate
from app.services import access, customer_service

router = APIRouter()


# NOTE: /me routes must stay above /{customer_id}
@router.get("/me", response_model=CustomerResponse)
def get_my_profile(customer: Customer = Depends(get_current_customer)):
    return customer


@router.put("/me", response_model=CustomerResponse)
def update_my_profile(
    payload: CustomerSelfUpdate,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    changes = payload.model_dump(exclude_unset=True)
    return customer_service.update_customer(db, customer, changes)


@router.get("", response_model=Page[CustomerResponse])
def list_customers(
    search: str | None = Query(None),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    items, total = customer_service.list_customers(db, params.offset, params.page_size, search)
    return Page(
        items=[CustomerResponse.model_validate(c) for c in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    access.authorize_customer_access(db, current_user, customer_id)
    return customer_service.get_customer(db, customer_id)


@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    payload: CustomerStaffUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    customer = customer_service.get_customer(db, customer_id)
    changes = payload.model_dump(exclude_unset=True)
    return customer_service.update_customer(db, customer, changes)