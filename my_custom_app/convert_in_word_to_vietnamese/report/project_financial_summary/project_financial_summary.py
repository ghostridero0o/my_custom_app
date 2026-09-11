import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate


PROFIT_AND_LOSS = "Profit and Loss"
CASH_FLOW = "Cash Flow"
NON_PROJECT = "non_project"
PROJECT_THRESHOLD_VALUES = (
    10_000_000,
    50_000_000,
    100_000_000,
    300_000_000,
    500_000_000,
)
DEFAULT_PROJECT_THRESHOLD = 50_000_000


def execute(filters=None):
    filters = frappe._dict(filters or {})
    normalize_filters(filters)
    validate_filters(filters)

    if filters.view_type == CASH_FLOW:
        projects, data = get_cash_flow_report(filters)
        columns = get_columns(projects, filters.company)
    else:
        projects, data = get_profit_and_loss_report(filters)
        columns = get_columns(projects, filters.company)

    return columns, data


def normalize_filters(filters):
    filters.view_type = filters.get("view_type") or PROFIT_AND_LOSS
    filters.project = normalize_multiselect(filters.get("project"))
    filters.hide_projects_below = cint(filters.get("hide_projects_below"))
    filters.project_threshold = flt(filters.get("project_threshold"))
    if filters.project_threshold not in PROJECT_THRESHOLD_VALUES:
        filters.project_threshold = DEFAULT_PROJECT_THRESHOLD


def normalize_multiselect(value):
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if item]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, list):
            return [item for item in parsed if item]
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def validate_filters(filters):
    if not filters.get("company"):
        frappe.throw(_("Company is required"))
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Both From Date and To Date are required"))
    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("From Date cannot be after To Date"))
    if filters.view_type not in (PROFIT_AND_LOSS, CASH_FLOW):
        frappe.throw(_("Invalid View Type"))


def get_base_conditions(filters, params):
    assigned_project_condition = """EXISTS (
        SELECT 1
        FROM `tabProject` project
        WHERE project.name = gle.project
            AND project.company = %(company)s
    )"""

    conditions = [
        "gle.company = %(company)s",
        "gle.posting_date BETWEEN %(from_date)s AND %(to_date)s",
        "gle.is_cancelled = 0",
    ]
    params.update(
        {
            "company": filters.company,
            "from_date": filters.from_date,
            "to_date": filters.to_date,
        }
    )

    if filters.project:
        params["projects"] = tuple(filters.project)
        assigned_project_condition = (
            f"(gle.project IN %(projects)s AND {assigned_project_condition})"
        )

    conditions.append(
        f"""(
            gle.project IS NULL
            OR gle.project = ''
            OR {assigned_project_condition}
        )"""
    )
    if filters.get("cost_center"):
        conditions.append("gle.cost_center = %(cost_center)s")
        params["cost_center"] = filters.cost_center
    if filters.get("finance_book"):
        conditions.append(
            "(gle.finance_book = %(finance_book)s OR gle.finance_book IS NULL OR gle.finance_book = '')"
        )
        params["finance_book"] = filters.finance_book
    else:
        conditions.append("(gle.finance_book IS NULL OR gle.finance_book = '')")

    return " AND ".join(conditions)


def get_projects(project_names, company):
    if not project_names:
        return []

    return frappe.get_all(
        "Project",
        filters={"name": ["in", list(project_names)], "company": company},
        fields=["name", "project_name"],
        order_by="project_name asc, name asc",
    )


def get_columns(projects, company):
    currency = frappe.get_cached_value("Company", company, "default_currency")
    columns = [
        {
            "fieldname": "account",
            "label": _("Account"),
            "fieldtype": "Link",
            "options": "Account",
            "width": 320,
            "sticky": True,
        },
        {
            "fieldname": "summary",
            "label": _("Summary"),
            "fieldtype": "Currency",
            "options": currency,
            "width": 150,
            "sticky": True,
        },
    ]

    columns.append(
        {
            "fieldname": NON_PROJECT,
            "label": _("Non Project"),
            "fieldtype": "Currency",
            "options": currency,
            "width": 150,
            "sticky": True,
        }
    )

    for project in projects:
        columns.append(
            {
                "fieldname": project.name,
                "label": project.project_name or project.name,
                "fieldtype": "Currency",
                "options": currency,
                "width": 150,
            }
        )
    return columns


def get_project_key(project):
    return project or NON_PROJECT


def add_project_amount(values, project, amount):
    project_key = get_project_key(project)
    values[project_key] = values.get(project_key, 0.0) + flt(amount)


def filter_small_projects(projects, filters, first_values, second_values):
    if not filters.hide_projects_below:
        return projects

    threshold = filters.project_threshold
    return {
        project
        for project in projects
        if abs(flt(first_values.get(project))) >= threshold
        or abs(flt(second_values.get(project))) >= threshold
    }


def get_profit_and_loss_report(filters):
    accounts = frappe.get_all(
        "Account",
        filters={
            "company": filters.company,
            "root_type": ["in", ["Income", "Expense"]],
        },
        fields=["name", "account_name", "root_type", "parent_account", "is_group", "lft"],
        order_by="lft asc",
    )
    if not accounts:
        return [], []

    params = {"accounts": tuple(account.name for account in accounts)}
    conditions = get_base_conditions(filters, params)
    entries = frappe.db.sql(
        f"""
        SELECT
            gle.account,
            gle.project,
            COALESCE(SUM(gle.debit_in_account_currency), 0) AS debit,
            COALESCE(SUM(gle.credit_in_account_currency), 0) AS credit
        FROM `tabGL Entry` gle
        WHERE {conditions}
            AND gle.account IN %(accounts)s
        GROUP BY gle.account, gle.project
        """,
        params,
        as_dict=True,
    )

    account_map = {account.name: account for account in accounts}
    balances = {}
    active_projects = set()
    active_accounts = set()
    total_income = {}
    total_expense = {}
    for entry in entries:
        account = account_map.get(entry.account)
        if not account:
            continue
        if account.root_type == "Income":
            amount = flt(entry.credit) - flt(entry.debit)
        elif account.root_type == "Expense":
            amount = flt(entry.debit) - flt(entry.credit)
        else:
            continue
        if amount:
            project_key = get_project_key(entry.project)
            balance_key = (entry.account, project_key)
            balances[balance_key] = balances.get(balance_key, 0.0) + amount
            active_accounts.add(entry.account)
            if project_key != NON_PROJECT:
                active_projects.add(project_key)
            if account.root_type == "Income":
                total_income[project_key] = total_income.get(project_key, 0.0) + amount
            elif account.root_type == "Expense":
                total_expense[project_key] = total_expense.get(project_key, 0.0) + amount

    active_projects = filter_small_projects(
        active_projects, filters, total_income, total_expense
    )
    projects = get_projects(active_projects, filters.company)
    value_keys = [project.name for project in projects] + [NON_PROJECT]

    # Include every ancestor of an account with activity so the report can render
    # a complete tree, even when a group account has a net value of zero.
    for account_name in list(active_accounts):
        parent_account = account_map[account_name].parent_account
        while parent_account and parent_account in account_map:
            active_accounts.add(parent_account)
            parent_account = account_map[parent_account].parent_account

    # GL Entries normally belong to leaf accounts. Roll their values up through
    # the account tree to calculate each group row for every project column.
    for account in reversed(accounts):
        if not account.parent_account or account.parent_account not in account_map:
            continue
        for project in value_keys:
            child_value = balances.get((account.name, project), 0.0)
            if child_value:
                parent_key = (account.parent_account, project)
                balances[parent_key] = balances.get(parent_key, 0.0) + child_value

    account_indents = get_account_indents(accounts, account_map)
    income_rows = []
    expense_rows = []

    for account in accounts:
        if account.name not in active_accounts:
            continue

        row = {
            "account": account.name,
            "parent_account": account.parent_account or "",
            "indent": account_indents[account.name],
            "is_group": account.is_group,
        }
        for project in value_keys:
            amount = balances.get((account.name, project), 0.0)
            row[project] = amount
        row["summary"] = sum(flt(row.get(project)) for project in value_keys)
        if account.root_type == "Income":
            income_rows.append(row)
        elif account.root_type == "Expense":
            expense_rows.append(row)

    data = income_rows
    data.append(make_total_row(_("Total Income"), value_keys, total_income, is_total=True))
    data.append(make_empty_row(value_keys))
    data.extend(expense_rows)
    data.append(make_total_row(_("Total Expense"), value_keys, total_expense, is_total=True))
    data.append(make_empty_row(value_keys))

    profit_or_loss = {
        project: total_income.get(project, 0.0) - total_expense.get(project, 0.0)
        for project in value_keys
    }
    data.append(make_total_row(_("Profit or Loss"), value_keys, profit_or_loss, is_total=True))
    return projects, data


def get_account_indents(accounts, account_map):
    indents = {}
    for account in accounts:
        indent = 0
        parent_account = account.parent_account
        while parent_account and parent_account in account_map:
            indent += 1
            parent_account = account_map[parent_account].parent_account
        indents[account.name] = indent
    return indents


def make_total_row(label, project_names, values, is_total=False):
    row = {"account": label, "is_total": is_total}
    for project in project_names:
        row[project] = values.get(project, 0.0)
    row["summary"] = sum(flt(row.get(project)) for project in project_names)
    return row


def make_empty_row(project_names):
    row = {"account": "", "summary": None}
    for project in project_names:
        row[project] = None
    return row


def get_cash_flow_report(filters):
    cash_accounts = frappe.get_all(
        "Account",
        filters={
            "company": filters.company,
            "account_type": ["in", ["Cash", "Bank"]],
            "is_group": 0,
            "disabled": 0,
        },
        pluck="name",
    )
    disbursement_accounts = frappe.get_all(
        "Account",
        filters={
            "company": filters.company,
            "account_number": ["in", ["3411", "3412"]],
            "is_group": 0,
        },
        pluck="name",
    )
    labor_accounts = frappe.get_all(
        "Account",
        filters={
            "company": filters.company,
            "account_number": ["in", ["6221", "6271", "6421"]],
            "is_group": 0,
        },
        pluck="name",
    )

    cash_in = {}
    cash_out = {}
    disbursement = {}
    direct_labor = {}

    if cash_accounts:
        params = {"accounts": tuple(cash_accounts)}
        conditions = get_base_conditions(filters, params)
        rows = frappe.db.sql(
            f"""
            SELECT
                gle.project,
                COALESCE(SUM(gle.debit), 0) AS cash_in,
                COALESCE(SUM(gle.credit), 0) AS cash_out
            FROM `tabGL Entry` gle
            WHERE {conditions}
                AND gle.account IN %(accounts)s
                AND (gle.voucher_subtype IS NULL OR gle.voucher_subtype != 'Internal Transfer')
            GROUP BY gle.project
            """,
            params,
            as_dict=True,
        )
        for row in rows:
            add_project_amount(cash_in, row.project, row.cash_in)
            add_project_amount(cash_out, row.project, row.cash_out)

    if disbursement_accounts:
        params = {"accounts": tuple(disbursement_accounts)}
        conditions = get_base_conditions(filters, params)
        rows = frappe.db.sql(
            f"""
            SELECT
                gle.project,
                COALESCE(SUM(gle.credit - gle.debit), 0) AS amount
            FROM `tabGL Entry` gle
            WHERE {conditions} AND gle.account IN %(accounts)s
            GROUP BY gle.project
            """,
            params,
            as_dict=True,
        )
        for row in rows:
            add_project_amount(disbursement, row.project, row.amount)

    if labor_accounts:
        params = {"accounts": tuple(labor_accounts), "labor_against": "%3349%"}
        conditions = get_base_conditions(filters, params)
        rows = frappe.db.sql(
            f"""
            SELECT
                gle.project,
                COALESCE(SUM(gle.debit - gle.credit), 0) AS amount
            FROM `tabGL Entry` gle
            WHERE {conditions}
                AND gle.account IN %(accounts)s
                AND gle.against LIKE %(labor_against)s
            GROUP BY gle.project
            """,
            params,
            as_dict=True,
        )
        for row in rows:
            add_project_amount(direct_labor, row.project, row.amount)

    candidate_projects = set(cash_in) | set(cash_out) | set(disbursement) | set(direct_labor)
    active_projects = {
        project
        for project in candidate_projects
        if project != NON_PROJECT
        and any(
            (
                cash_in.get(project, 0.0),
                cash_out.get(project, 0.0),
                disbursement.get(project, 0.0),
                direct_labor.get(project, 0.0),
            )
        )
    }
    active_projects = filter_small_projects(active_projects, filters, cash_in, cash_out)
    projects = get_projects(active_projects, filters.company)
    value_keys = [project.name for project in projects] + [NON_PROJECT]

    net_cash_flow = {
        project: cash_in.get(project, 0.0)
        - cash_out.get(project, 0.0)
        - disbursement.get(project, 0.0)
        - direct_labor.get(project, 0.0)
        for project in value_keys
    }
    data = [
        make_total_row(_("Cash In"), value_keys, cash_in),
        make_total_row(_("Cash Out"), value_keys, cash_out),
        make_total_row(_("Các khoản giải ngân để thanh toán"), value_keys, disbursement),
        make_total_row(_("Nhân công trực tiếp"), value_keys, direct_labor),
        make_total_row(_("Net Cash Flow"), value_keys, net_cash_flow),
    ]
    return projects, data
