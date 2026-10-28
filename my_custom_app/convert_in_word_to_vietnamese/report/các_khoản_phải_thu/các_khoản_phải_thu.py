"""Vietnamese receivable report with native filters and separate cash measures."""
from my_custom_app.controllers.filtered_party_report import (
    cash_shares,
    project_share,
    execute as execute_report,
)


def execute(filters=None):
    return execute_report(filters, account_type="Receivable")
