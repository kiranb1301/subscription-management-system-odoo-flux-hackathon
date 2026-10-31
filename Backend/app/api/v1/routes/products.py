from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import PageParams, get_current_user, require_admin
from app.core.permissions import is_staff
from app.db.session import get_db
from app.models import User
from app.schemas.common import Page
from app.schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
    VariantUpdate,
)
from app.services import product_service

router = APIRouter()


@router.get("", response_model=Page[ProductResponse])
def list_products(
    search: str | None = Query(None),
    is_active: bool | None = Query(None, description="Staff only; ignored for customers"),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    staff = is_staff(current_user)
    items, total = product_service.list_products(
        db, params.offset, params.page_size, staff, search, is_active
    )
    return Page(
        items=[ProductResponse.from_product(p, staff) for p in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    staff = is_staff(current_user)
    return ProductResponse.from_product(product_service.get_product(db, product_id, staff), staff)


@router.post("", response_model=ProductResponse, status_code=201)
def create_product(
    payload: ProductCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    return ProductResponse.from_product(product_service.create_product(db, payload), True)


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return ProductResponse.from_product(
        product_service.update_product(db, product_id, payload), True
    )


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    product_service.delete_product(db, product_id)


# ---------- variants (nested) ----------
@router.post("/{product_id}/variants", response_model=VariantResponse, status_code=201)
def create_variant(
    product_id: int,
    payload: VariantCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return product_service.create_variant(db, product_id, payload)


@router.put("/{product_id}/variants/{variant_id}", response_model=VariantResponse)
def update_variant(
    product_id: int,
    variant_id: int,
    payload: VariantUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return product_service.update_variant(db, product_id, variant_id, payload)


@router.delete("/{product_id}/variants/{variant_id}", status_code=204)
def deactivate_variant(
    product_id: int,
    variant_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    product_service.deactivate_variant(db, product_id, variant_id)