from datetime import date, timedelta

try:
    from tests.test_payments import _set_invoice, confirmed_invoice, world  # noqa: F401
except ImportError:  # tests folder is not a package
    from test_payments import _set_invoice, confirmed_invoice, world  # noqa: F401

from app.tasks.scheduler import build_scheduler, run_daily_jobs

API = "/api/v1"


def test_scheduler_registers_one_daily_job_and_is_off_by_default():
    scheduler = build_scheduler()
    assert [job.id for job in scheduler.get_jobs()] == ["daily-billing"]
    assert scheduler.running is False


def test_daily_jobs_skip_billing_without_admin(session_factory):
    with session_factory() as db:
        assert run_daily_jobs(db) == {"billing_status": "SKIPPED", "invoices_created": 0, "reminders": 0}


def test_daily_jobs_remind_once_per_day(api, world, session_factory):
    w = world
    inv = confirmed_invoice(api, w, "b")
    _set_invoice(session_factory, inv["id"], due_date=date.today() - timedelta(days=2))

    with session_factory() as db:
        first = run_daily_jobs(db)
    assert first["billing_status"] == "COMPLETED" and first["reminders"] == 1

    with session_factory() as db:
        assert run_daily_jobs(db)["reminders"] == 0  # already reminded today

    titles = [n["title"] for n in api.get(f"{API}/notifications", headers=w["b"]).json()["items"]]
    assert "Payment reminder" in titles
    assert api.get(f"{API}/notifications", headers=w["a"]).json()["total"] == 0