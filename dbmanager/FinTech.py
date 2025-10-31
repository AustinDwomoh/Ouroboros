from datetime import datetime, timedelta
from settings import ErrorHandler
from .pg_client import create_connection as _create_connection


def create_connection(db_path="data/finance.db"):
    # db_path ignored in Postgres-only mode
    return _create_connection()


def create_money_table(user_id=None):
    """No-op for Postgres: schema should be applied via migrations/pg_schema.sql."""
    # Ensure user_payments exists (schema should already handle this). If not, create it.
    with create_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_payments (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL UNIQUE
            )
            """
        )
        conn.commit()

def calculate_next_due_date(due_date: str, frequency: str) -> str:
    """Calculates the next due date based on frequency and last paid date"""
    try:
        date_obj = datetime.strptime(due_date, "%Y-%m-%d")
        if frequency == "Monthly":
            next_due = date_obj + timedelta(days=30)
        elif frequency == "Bi-Weekly":
            next_due = date_obj + timedelta(days=14)
        elif frequency == "Weekly":
            next_due = date_obj + timedelta(days=7)
        else:
            return due_date  # One-time payments stay the same

        return next_due.strftime("%Y-%m-%d")
    except ValueError:
        return due_date  # Return as-is if date format is incorrect

def update_user_ids(user_id):
    with create_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM user_payments WHERE user_id = %s", (user_id,))
        existing = c.fetchone()
        if not existing:
            c.execute("INSERT INTO user_payments (user_id) VALUES (%s)", (user_id,))
        conn.commit()

def fintech_list(user_id):
    """Return fintech payments for a user from centralized `fintech_payments`."""
    with create_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, category, amount, total_paid, status, frequency, due_date, last_paid_date FROM fintech_payments WHERE user_id = %s", (user_id,))
        return c.fetchall()

def update_table(user_id, name, category, amount, due_date, status, frequency="One-Time"):
    """Insert or update a fintech payment for a user in centralized `fintech_payments`."""
    update_user_ids(user_id)
    with create_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, total_paid, frequency, due_date FROM fintech_payments WHERE user_id = %s AND name = %s", (user_id, name))
        existing = c.fetchone()
        if existing:
            pid, total_paid, existing_freq, existing_due = existing
            freq = existing_freq or frequency
            new_due_date = calculate_next_due_date(existing_due or due_date, freq)
            last_paid_date = datetime.today().strftime("%Y-%m-%d")
            c.execute(
                "UPDATE fintech_payments SET category = COALESCE(%s, category), total_paid = COALESCE(total_paid, 0) + %s, due_date = COALESCE(%s, due_date), last_paid_date = COALESCE(%s, last_paid_date), status = COALESCE(%s, status), frequency = %s WHERE id = %s",
                (category, amount, new_due_date, last_paid_date, status, freq, pid),
            )
            conn.commit()
            return new_due_date, (0 if total_paid is None else total_paid) + amount
        else:
            c.execute(
                "INSERT INTO fintech_payments (user_id, name, category, amount, due_date, frequency, status, total_paid) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (user_id, name, category, amount, due_date, frequency, status, 0),
            )
            conn.commit()
            return due_date, amount

def update_payment_status(user_id, payment_name, status):
    with create_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE fintech_payments SET status = %s WHERE user_id = %s AND name = %s", (status, user_id, payment_name))
        conn.commit()

def check_due_dates():
    try:
        today = datetime.today().strftime("%Y-%m-%d")
        upcoming_date = (datetime.today() + timedelta(days=7)).strftime("%Y-%m-%d")
        reminders = []
        with create_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT DISTINCT user_id FROM user_payments")
            user_ids = [row[0] for row in c.fetchall()]
            if not user_ids:
                return []
            c.execute(
                "SELECT user_id, name, category, amount, due_date, status FROM fintech_payments WHERE status != 'paid' AND status = 'active' AND due_date IS NOT NULL AND due_date BETWEEN %s AND %s ORDER BY due_date ASC",
                (today, upcoming_date),
            )
            rows = c.fetchall()
            for user_id, name, category, amount, due_date, status in rows:
                reminders.append({
                    "user_id": user_id,
                    "name": name,
                    "category": category,
                    "amount": amount,
                    "due_date": due_date,
                    "status": status,
                })
        return reminders
    except Exception as e:
        ErrorHandler().handle(e, context="Error in check_due_dates function")
        return []

