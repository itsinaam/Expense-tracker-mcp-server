from fastmcp import FastMCP
import random

mcp = FastMCP(name="demo server")

@mcp.tool
def dice_roll(sides: int = 6):
    """Roll a dice with the given number of sides."""
    return random.randint(1, sides)


@mcp.tool
def add_numbers(a: int, b: int):
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)