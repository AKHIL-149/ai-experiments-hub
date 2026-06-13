"""
Sample clean Python code for testing parser.

This file contains well-written code without security issues or code smells.
"""
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class User:
    """Represents a user in the system"""
    id: int
    username: str
    email: str
    is_active: bool = True


def calculate_total(prices: List[float], tax_rate: float = 0.1) -> float:
    """
    Calculate total price including tax.

    Args:
        prices: List of item prices
        tax_rate: Tax rate as decimal (default 0.1 for 10%)

    Returns:
        Total price with tax applied
    """
    subtotal = sum(prices)
    tax = subtotal * tax_rate
    return subtotal + tax


def validate_email(email: str) -> bool:
    """
    Validate email format.

    Args:
        email: Email address to validate

    Returns:
        True if email is valid, False otherwise
    """
    if not email or '@' not in email:
        return False

    parts = email.split('@')
    if len(parts) != 2:
        return False

    local, domain = parts
    return len(local) > 0 and '.' in domain


class UserManager:
    """Manages user operations"""

    def __init__(self):
        self.users: List[User] = []

    def add_user(self, user: User) -> None:
        """Add a user to the system"""
        self.users.append(user)

    def find_user(self, user_id: int) -> Optional[User]:
        """Find user by ID"""
        for user in self.users:
            if user.id == user_id:
                return user
        return None

    def get_active_users(self) -> List[User]:
        """Get all active users"""
        return [u for u in self.users if u.is_active]


async def fetch_data(url: str) -> dict:
    """
    Fetch data from URL asynchronously.

    Args:
        url: URL to fetch from

    Returns:
        Response data as dictionary
    """
    # Simulated async operation
    return {"status": "success", "url": url}


def main():
    """Main entry point"""
    manager = UserManager()

    user = User(
        id=1,
        username="testuser",
        email="test@example.com"
    )

    manager.add_user(user)
    print(f"Added user: {user.username}")


if __name__ == "__main__":
    main()
