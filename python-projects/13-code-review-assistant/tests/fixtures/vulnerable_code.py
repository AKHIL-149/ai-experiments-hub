"""
Vulnerable Python code for testing analyzers.

This file intentionally contains security vulnerabilities and code smells
for testing the analysis engine.
"""
import os
import pickle
import subprocess
import hashlib
from hashlib import md5, sha1


# SEC004: Hardcoded secrets
# Note: These are fake test keys, not real credentials
API_KEY = "sk_test_abc123456789xyz"  # Using test key prefix
PASSWORD = "admin123"
SECRET_TOKEN = "test_token_1234567890abcdef"


# SEC002: SQL Injection vulnerability
def get_user_by_name(username):
    """Vulnerable to SQL injection"""
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    return execute_query(query)


def search_users(search_term):
    """Another SQL injection example"""
    sql = f"SELECT * FROM users WHERE name LIKE '%{search_term}%'"
    return execute_query(sql)


# SEC003: Command injection vulnerability
def run_command(user_input):
    """Vulnerable to command injection"""
    os.system("ls " + user_input)


def execute_shell(cmd):
    """Another command injection"""
    subprocess.call(cmd, shell=True)


# SEC005: Path traversal vulnerability
def read_file(filename):
    """Vulnerable to path traversal"""
    with open("/var/data/" + filename, 'r') as f:
        return f.read()


def get_user_file(user_input):
    """Another path traversal example"""
    file_path = os.path.join('/app/data', user_input)
    return open(file_path).read()


def load_config(config_name):
    """Path traversal with f-string"""
    path = f"/etc/configs/{config_name}"
    with open(path) as f:
        return f.read()


# SEC006: Unsafe deserialization
def load_data(data):
    """Vulnerable to pickle exploit"""
    return pickle.loads(data)


def evaluate_expression(expr):
    """Dangerous use of eval"""
    return eval(expr)


def run_user_code(code):
    """Dangerous use of exec"""
    exec(code)


# SEC007: Weak cryptography
def hash_password(password):
    """Using weak MD5 for passwords"""
    return md5(password.encode()).hexdigest()


def generate_token(data):
    """Using weak SHA1"""
    return sha1(data.encode()).hexdigest()


def create_checksum(content):
    """Using hashlib.md5() directly"""
    return hashlib.md5(content.encode()).digest()


# SMELL001: Long method (>50 lines)
def process_order(order_id, customer_id, items, shipping_address, billing_address,
                 payment_method, discount_code, gift_wrap, special_instructions):
    """Method with too many lines and parameters"""
    # Validate customer
    if not customer_id:
        return None

    # Check inventory
    for item in items:
        if not check_stock(item):
            return None

    # Calculate prices
    subtotal = 0
    for item in items:
        subtotal += item['price'] * item['quantity']

    # Apply discount
    if discount_code:
        discount = calculate_discount(discount_code)
        subtotal = subtotal - (subtotal * discount)

    # Calculate tax
    tax = subtotal * 0.1

    # Add shipping
    shipping = calculate_shipping(shipping_address)

    # Add gift wrap
    if gift_wrap:
        shipping += 5.00

    total = subtotal + tax + shipping

    # Process payment
    payment_result = process_payment(payment_method, total)
    if not payment_result:
        return None

    # Create shipment
    shipment = create_shipment(shipping_address, items)

    # Send notifications
    send_confirmation_email(customer_id)
    send_sms_notification(customer_id)

    # Update inventory
    for item in items:
        update_stock(item)

    # Log transaction
    log_transaction(order_id, total)

    # Update customer points
    update_loyalty_points(customer_id, total)

    return {"order_id": order_id, "total": total}


# SMELL002: Deep nesting (>4 levels)
def complex_validation(data):
    """Function with deep nesting"""
    if data:
        if 'user' in data:
            if data['user']:
                if 'permissions' in data['user']:
                    if data['user']['permissions']:
                        if 'admin' in data['user']['permissions']:
                            return True
    return False


# SMELL003: God class (too many methods and responsibilities)
class ApplicationManager:
    """Class doing too many things"""

    def __init__(self):
        self.users = []
        self.orders = []
        self.products = []
        self.payments = []

    def add_user(self, user): pass
    def update_user(self, user): pass
    def delete_user(self, user_id): pass
    def authenticate_user(self, username, password): pass
    def reset_password(self, email): pass
    def send_welcome_email(self, user): pass

    def create_order(self, order): pass
    def cancel_order(self, order_id): pass
    def update_order_status(self, order_id, status): pass
    def calculate_order_total(self, order): pass

    def add_product(self, product): pass
    def update_product_price(self, product_id, price): pass
    def check_product_availability(self, product_id): pass

    def process_payment(self, payment): pass
    def refund_payment(self, payment_id): pass
    def generate_invoice(self, order_id): pass

    def send_notification(self, user_id, message): pass
    def log_activity(self, activity): pass
    def generate_report(self, report_type): pass
    def export_data(self, format): pass
    def import_data(self, file): pass
    def backup_database(self): pass


# SMELL004: Magic numbers
def calculate_score(points):
    """Function with magic numbers"""
    if points > 1000:
        return points * 1.5
    elif points > 500:
        return points * 1.25
    elif points > 100:
        return points * 1.1
    return points


# COMPLEX001: High cyclomatic complexity
def complex_function(a, b, c, d, e):
    """Function with high complexity"""
    result = 0

    if a > 0:
        if b > 0:
            result += a * b
        else:
            result += a

    if c > 0:
        if d > 0:
            result += c * d
        else:
            result += c

    if e > 0:
        result *= e

    for i in range(10):
        if i % 2 == 0:
            result += i
        else:
            result -= i

    while result > 100:
        result /= 2

    try:
        result = result / a
    except:
        result = 0

    return result


# Helper functions (stubs)
def execute_query(query): return []
def check_stock(item): return True
def calculate_discount(code): return 0.1
def calculate_shipping(address): return 10.0
def process_payment(method, amount): return True
def create_shipment(address, items): return {}
def send_confirmation_email(customer_id): pass
def send_sms_notification(customer_id): pass
def update_stock(item): pass
def log_transaction(order_id, total): pass
def update_loyalty_points(customer_id, total): pass
