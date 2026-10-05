from decimal import Decimal, InvalidOperation


def parse_price(value: str) -> Decimal:
    try:
        price = Decimal(value.replace(",", "."))
    except InvalidOperation as error:
        raise ValueError("Enter a valid price") from error
    if price < 0:
        raise ValueError("Price cannot be negative")
    return price.quantize(Decimal("0.01"))
