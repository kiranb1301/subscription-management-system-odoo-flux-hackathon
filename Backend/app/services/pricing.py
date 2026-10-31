from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def line_amounts(unit_price, quantity: int, discount, tax_rate) -> tuple[Decimal, Decimal, Decimal]:
    """Returns (taxable, tax, total) for one line. Tax is charged after the line discount."""
    gross = money(Decimal(unit_price) * quantity)
    taxable = gross - money(discount)
    tax = money(taxable * Decimal(tax_rate) / HUNDRED)
    return taxable, tax, taxable + tax