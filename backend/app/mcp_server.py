"""
mcp_server.py — exposes the five MCP tools via the official MCP Python SDK.
This runs as a standalone process separate from the FastAPI server.
The AI Buyer client connects to this server to discover and call tools.
"""
import asyncio
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

GATEWAY_BASE_URL = "http://localhost:8000"

server = Server("ai-commerce-gateway")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_catalog",
            description="Search a merchant's product catalog by keyword and/or price ceiling.",
            inputSchema={
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string", "description": "Merchant identifier"},
                    "query": {"type": "string", "description": "Keyword to match against product name, category, or description"},
                    "max_price": {"type": "number", "description": "Maximum price in INR (optional)"},
                },
                "required": ["merchant_id"],
            },
        ),
        types.Tool(
            name="get_product",
            description="Fetch a single product by ID from a merchant's active catalog.",
            inputSchema={
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string"},
                    "product_id": {"type": "string"},
                },
                "required": ["merchant_id", "product_id"],
            },
        ),
        types.Tool(
            name="build_cart",
            description="Build a cart for a product. Applies upsell logic if the merchant has enabled it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string"},
                    "mandate_id": {"type": "string", "description": "Buyer's spending mandate ID"},
                    "product_id": {"type": "string"},
                    "quantity": {"type": "integer", "default": 1},
                    "customer_request": {"type": "string", "description": "Original buyer intent string"},
                },
                "required": ["merchant_id", "mandate_id", "product_id"],
            },
        ),
        types.Tool(
            name="check_policy",
            description=(
                "Run Mandate Check (buyer-side authority) and Policy Gate (merchant rules) for a cart. "
                "Returns APPROVE or BLOCK with reasons for each check."
            ),
            inputSchema={
                "type": "object",
                "properties": {"cart_id": {"type": "string"}},
                "required": ["cart_id"],
            },
        ),
        types.Tool(
            name="checkout",
            description=(
                "Execute checkout for an APPROVED cart. Calls Razorpay (test mode), "
                "verifies the payment, and returns a Decision Receipt. "
                "If the cart is BLOCKED, returns the receipt with blocked_reason and Razorpay is never called."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cart_id": {"type": "string"},
                    "customer_request": {"type": "string"},
                    "products_considered": {"type": "integer"},
                    "selection_reasons": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["cart_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    async with httpx.AsyncClient(base_url=GATEWAY_BASE_URL, timeout=30) as client:
        endpoint = f"/mcp/{name}"
        response = await client.post(endpoint, json=arguments)
        response.raise_for_status()
        return [types.TextContent(type="text", text=response.text)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
