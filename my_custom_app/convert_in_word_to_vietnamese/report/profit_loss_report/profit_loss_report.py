import frappe
from frappe import _
from frappe.utils import flt
import json


@frappe.whitelist()
def execute(filters):
    # Validate the filters
    validate_filters(filters)
    
    # Get the list of accounts and projects
    accounts = get_accounts(filters)
    projects = get_projects()

    # Get the GL entries and group them by account
    gl_entries_by_account = get_gl_entries(filters, accounts)
    
    # Generate the columns for the report
    columns = get_columns(projects)

    # Prepare the data for the report
    report_data = prepare_data(accounts, projects, gl_entries_by_account, filters)
    
    # Calculate Profit or Loss and append it to the report
    profit_or_loss_row = calculate_profit_or_loss(accounts, projects, gl_entries_by_account, filters)
    report_data.append(profit_or_loss_row)
    
    # Return the result
    return columns, report_data
    
def validate_filters(filters):
    """Validate the filters"""
    if not filters.get('from_date') or not filters.get('to_date'):
        raise ValueError("Both from_date and to_date are required in filters.")

def get_accounts(filters):
    """Fetch accounts with 'Profit and Loss' report_type"""
    return frappe.get_all('Account', filters={'report_type': 'Profit and Loss'}, fields=['name', 'account_name', 'root_type', 'is_group', 'parent_account'])


def get_projects():
    """Fetch the list of projects"""
    return frappe.get_all('Project', fields=['name', 'project_name'])


def get_gl_entries(filters, accounts):
    """Fetch GL entries based on filters and accounts"""
    gl_entries_by_account = {}

    # Escape the Cost Center filter properly
    cost_center = filters.get('cost_center')
    condition = ""
    if cost_center:
        cost_center_escaped = frappe.db.escape(cost_center)
        condition = f"AND cost_center = {cost_center_escaped}"

    # Query GL Entry data
    gl_entries = frappe.db.sql(
        """
        SELECT 
            posting_date, account, project, cost_center, debit_in_account_currency, credit_in_account_currency
        FROM 
            `tabGL Entry`
        WHERE 
            posting_date BETWEEN %s AND %s
            AND account IN ({})
            AND is_cancelled = 0
        {}
        """.format(", ".join([frappe.db.escape(account['name']) for account in accounts]), condition),
        (filters.get('from_date'), filters.get('to_date')),
        as_dict=True
    )

    # Group entries by account
    for entry in gl_entries:
        gl_entries_by_account.setdefault(entry['account'], []).append(entry)

    return gl_entries_by_account


def get_columns(projects):
    """Generate columns for the report, including project columns"""
    columns = [
        {
            'fieldname': 'account',
            'label': _('Account'),
            'fieldtype': 'Link',
            'options': 'Account'
        },
        {
            'fieldname': 'account_title',
            'label': _('Account Title'),
            'fieldtype': 'Data'
        }
    ]

    # Add columns for each project
    for project in projects:
        columns.append({
            'fieldname': project['name'],
            'label': project['project_name'],
            'fieldtype': 'Currency',
            'options': 'currency'
        })

    return columns


def prepare_data(accounts, projects, gl_entries_by_account, filters):
    """Prepare the data for the report"""
    income_accounts = []
    expense_accounts = []
    report_data = []

    total_income = {project['name']: 0 for project in projects}  # To store the total of income accounts by project
    total_expense = {project['name']: 0 for project in projects}  # To store the total of expense accounts by project

    for account in accounts:
        account_name = account['name']
        row = {
            'account': account_name,
            'account_title': account['account_name']
        }

        total_balance = {project['name']: 0 for project in projects}  # Track balance per project for each account

        # Calculate the balance for each project and account
        for project in projects:
            project_id = project['name']
            balance = 0

            # Loop over GL entries for the current account
            if account_name in gl_entries_by_account:
                for entry in gl_entries_by_account[account_name]:
                    if entry['project'] == project_id:
                        if account['root_type'] == "Income":
                            balance += flt(entry['credit_in_account_currency']) - flt(entry['debit_in_account_currency'])
                        else:
                            balance += flt(entry['debit_in_account_currency']) - flt(entry['credit_in_account_currency'])

            row[project_id] = balance
            total_balance[project_id] += balance

        # Only add account if balance is not zero
        if any(val != 0 for val in total_balance.values()):
            if account['root_type'] == "Income":
                income_accounts.append(row)
                for project in projects:
                    total_income[project['name']] += total_balance[project['name']]
            elif account['root_type'] == "Expense":
                expense_accounts.append(row)
                for project in projects:
                    total_expense[project['name']] += total_balance[project['name']]

    # Sort accounts by 'is_group' (groups come first) and account type (Income, then Expense)
    income_accounts.sort(key=lambda x: 1 if x['account'].split(' - ')[0].startswith('group') else 0)
    expense_accounts.sort(key=lambda x: 1 if x['account'].split(' - ')[0].startswith('group') else 0)

    # Add sorted data into the report data
    report_data.extend(income_accounts)
    
    # Add the "Total Income" row
    total_income_row = {
        'account': _('Total Income'),
        'account_title': _('Total Income'),
    }
    for project in projects:
        total_income_row[project['name']] = total_income[project['name']]

    report_data.append(total_income_row)
    
    # Add an empty row after Total Income
    empty_row = {
        'account': '',
        'account_title': '',
    }
    for project in projects:
        empty_row[project['name']] = ""
    report_data.append(empty_row)

    report_data.extend(expense_accounts)
    
    # Add the "Total Expense" row
    total_expense_row = {
        'account': _('Total Expense'),
        'account_title': _('Total Expense'),
    }
    for project in projects:
        total_expense_row[project['name']] = total_expense[project['name']]

    report_data.append(total_expense_row)
    
    # Add an empty row after Total Expense
    empty_row = {
        'account': '',
        'account_title': '',
    }
    for project in projects:
        empty_row[project['name']] = ""
    report_data.append(empty_row)

    return report_data


def calculate_profit_or_loss(accounts, projects, gl_entries_by_account, filters):
    """Calculate Profit or Loss for each project"""
    profit_or_loss_row = {
        'account': _('Profit or Loss'),
        'account_title': _('Profit or Loss'),
    }

    for project in projects:
        project_id = project['name']
        income_total = 0
        expense_total = 0
        
        for account in accounts:
            account_name = account['name']
            if account['root_type'] == "Income":
                if account_name in gl_entries_by_account:
                    for entry in gl_entries_by_account[account_name]:
                        if entry['project'] == project_id:
                            income_total += flt(entry['credit_in_account_currency']) - flt(entry['debit_in_account_currency'])
            elif account['root_type'] == "Expense":
                if account_name in gl_entries_by_account:
                    for entry in gl_entries_by_account[account_name]:
                        if entry['project'] == project_id:
                            expense_total += flt(entry['debit_in_account_currency']) - flt(entry['credit_in_account_currency'])

        profit_or_loss_row[project_id] = income_total - expense_total

    return profit_or_loss_row
