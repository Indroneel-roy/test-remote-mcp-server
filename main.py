from fastmcp import FastMCP
import random
import json

mcp = FastMCP("Simple Calculator Server")

@mcp.tool
def add(a: float, b: float) -> float:
    return a + b

@mcp.tool
def random_number(min_value: int, max_value: int) -> int:
    return random.randint(min_value, max_value)

@mcp.resource("info://server")
def server_info() -> str:
    info = {
        "name": "Simple Calculator Server",
        "version": "1.0",
        "description": "A server that provides basic calculator functions and random number generation.",
        "tools": ["add", "random_number"],
        "authors": ["Your Name"]
    }
    return json.dumps(info, indent=2)

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)  # Changed to 3001