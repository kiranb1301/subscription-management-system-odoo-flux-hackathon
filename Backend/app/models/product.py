from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    BigInt,
    IdMixin,
    Money,
    SoftDeleteMixin,
    TimestampMixin,
    enum_type,
)
from app.models.enums import ProductType


class Product(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    product_type: Mapped[ProductType] = mapped_column(
        enum_type(ProductType, 50), default=ProductType.SERVICE, nullable=False
    )
    sales_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    cost_price: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    product_taxes: Mapped[list["ProductTax"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductVariant(IdMixin, TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "variant_name"),)

    product_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    additional_price: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0.00"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variants")
    options: Mapped[list["ProductVariantOption"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )

    @property
    def final_price(self) -> Decimal:
        """FinalPrice = SalesPrice + VariantPrice"""
        return self.product.sales_price + self.additional_price


class ProductVariantOption(IdMixin, Base):
    __tablename__ = "product_variant_options"

    variant_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    option_name: Mapped[str] = mapped_column(String(100), nullable=False)
    option_value: Mapped[str] = mapped_column(String(100), nullable=False)

    variant: Mapped["ProductVariant"] = relationship(back_populates="options")