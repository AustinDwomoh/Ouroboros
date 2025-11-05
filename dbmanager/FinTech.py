from datetime import datetime, timedelta
from settings import ErrorHandler, create_async_pg_conn,ensure_user

error_handler = ErrorHandler()


# -------------------------------------------------------------
# UTILITIES
# -------------------------------------------------------------
def calculate_next_due_date(due_date: str, frequency: str) -> str:
    """Calculate the next due date from a given due date + frequency."""
    try:
        date_obj = datetime.strptime(due_date, "%Y-%m-%d")
        freq = frequency.lower()
        if freq == "monthly":
            next_due = date_obj + timedelta(days=30)
        elif freq in ("bi-weekly", "biweekly"):
            next_due = date_obj + timedelta(days=14)
        elif freq == "weekly":
            next_due = date_obj + timedelta(days=7)
        elif freq == "daily":
            next_due = date_obj + timedelta(days=1)
        else:
            return due_date  # one-time or yearly stays same
        return next_due.strftime("%Y-%m-%d")
    except Exception:
        return due_date


# -------------------------------------------------------------
# CRUD / FINTECH OPERATIONS
# -------------------------------------------------------------
async def fintech_list(user_id: int):
    """Fetch all fintech payments for a given user."""
    conn = await create_async_pg_conn()
    await ensure_user(user_id)
    try:
        rows = await conn.fetch("""
            SELECT id, name, category, amount, total_paid,
                   status, frequency, due_date, last_paid_date
            FROM fintech_payments
            WHERE user_id = $1
            ORDER BY due_date ASC NULLS LAST
        """, user_id)
        return [dict(r) for r in rows]
    except Exception as e:
        error_handler.handle(e, context=f"fintech_list({user_id})")
        return []
    finally:
        await conn.close()


async def update_payment(user_id: int, name: str, category: str,
                         amount: float, due_date: str,
                         status: str, frequency="once"):
    """
    Insert or update a user's fintech payment record.
    """
    conn = await create_async_pg_conn()
    await ensure_user(user_id)
    try:
        row = await conn.fetchrow("""
            SELECT id, total_paid, frequency, due_date
            FROM fintech_payments
            WHERE user_id = $1 AND name ILIKE $2
        """, user_id, name)

        if row:
            # existing payment — update totals/dates
            total_paid = row["total_paid"] or 0
            existing_due = row["due_date"] or due_date
            freq = (row["frequency"] or frequency).lower()
            new_due = calculate_next_due_date(existing_due, freq)
            last_paid = datetime.now().strftime("%Y-%m-%d")

            await conn.execute("""
                UPDATE fintech_payments
                SET category = COALESCE($1, category),
                    total_paid = $2,
                    due_date = $3,
                    last_paid_date = $4,
                    status = $5,
                    frequency = $6,
                    updated_at = now()
                WHERE id = $7
            """, category, total_paid + amount, new_due, last_paid,
                 status, freq, row["id"])
            return {"updated_due": new_due, "new_total": total_paid + amount}
        else:
            # new payment
            await conn.execute("""
                INSERT INTO fintech_payments
                    (user_id, name, category, amount, due_date,
                     frequency, status, total_paid)
                VALUES ($1,$2,$3,$4,$5,$6,$7,0)
            """, user_id, name, category, amount, due_date,
                 frequency.lower(), status)
            return {"inserted": True, "due_date": due_date}
    except Exception as e:
        error_handler.handle(e, context="update_payment")
        return {}
    finally:
        await conn.close()


async def update_payment_status(user_id: int, name: str, status: str):
    """Change payment status (pending → paid, overdue → paid, etc.)."""
    conn = await create_async_pg_conn()
    await ensure_user(user_id)
    try:
        await conn.execute("""
            UPDATE fintech_payments
            SET status = $1, updated_at = now()
            WHERE user_id = $2 AND name ILIKE $3
        """, status, user_id, name)
        return True
    except Exception as e:
        error_handler.handle(e, context="update_payment_status")
        return False
    finally:
        await conn.close()


# -------------------------------------------------------------
# DUE-DATE REMINDERS
# -------------------------------------------------------------
async def check_due_dates():
    """
    Find upcoming payments within 7 days that are active and not yet paid.
    """
    conn = await create_async_pg_conn()
    reminders = []
    try:
        today = datetime.now().date()
        week_ahead = today + timedelta(days=7)

        rows = await conn.fetch("""
            SELECT user_id, name, category, amount,
                   due_date, status, frequency
            FROM fintech_payments
            WHERE status IN ('pending','active')
              AND due_date BETWEEN $1 AND $2
            ORDER BY due_date ASC
        """, today, week_ahead)

        for r in rows:
            reminders.append({
                "user_id": r["user_id"],
                "name": r["name"],
                "category": r["category"],
                "amount": float(r["amount"]),
                "due_date": r["due_date"].strftime("%Y-%m-%d") if r["due_date"] else None,
                "status": r["status"],
                "frequency": r["frequency"]
            })
        return reminders
    except Exception as e:
        error_handler.handle(e, context="check_due_dates")
        return []
    finally:
        await conn.close()
