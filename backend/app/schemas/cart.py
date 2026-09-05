from pydantic import BaseModel


class CartItem(BaseModel):
    product_id: str
    quantity: int
    unit_price_inr: float


class Cart(BaseModel):
    cart_id: str
    merchant_id: str
    mandate_id: str
    items: list[CartItem]
    upsell_items: list[CartItem]
    total_inr: float
    idempotency_key: str


class BuildCartRequest(BaseModel):
    merchant_id: str
    mandate_id: str
    product_id: str
    quantity: int = 1
    customer_request: str = ""
