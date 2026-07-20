import frappe
from frappe.desk.reportview import get_match_cond


def get_settings():
	# Business settings may be changed while workers are running. Read the
	# current Single value so a newly selected bot/channel takes effect at once.
	return frappe.get_single("Raven Accounting Settings")


def get_channel_settings(channel=None):
	"""Return the accounting defaults for a Raven channel, with legacy fallback."""
	settings = get_settings()
	if channel:
		for row in settings.get("channel_configurations") or []:
			if row.channel == channel:
				return row
	return settings


@frappe.whitelist()
def get_company_accounting_defaults(company):
	if not company or not frappe.db.exists("Company", company):
		return {}
	company_doc = frappe.get_cached_doc("Company", company)
	cash_account_number = frappe.db.get_value("Account", company_doc.default_cash_account, "account_number")
	modes = frappe.get_all(
		"Mode of Payment Account",
		filters={"company": company, "default_account": ["is", "set"]},
		pluck="parent",
	)
	active_modes = frappe.get_all(
		"Mode of Payment",
		filters={"name": ["in", modes], "enabled": 1},
		order_by="name asc",
		pluck="name",
	) if modes else []
	return {
		"cash_account": cash_account_number,
		"cost_center": company_doc.cost_center,
		"available_mode_of_payments": active_modes,
		"mode_of_payment": active_modes[0] if len(active_modes) == 1 else None,
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_company_mode_of_payment(doctype, txt, searchfield, start, page_len, filters):
	company = (filters or {}).get("company")
	if not company:
		return []
	return frappe.db.sql(
		"""
		select distinct `tabMode of Payment`.name, mpa.default_account
		from `tabMode of Payment`
		inner join `tabMode of Payment Account` mpa on mpa.parent = `tabMode of Payment`.name
		inner join `tabAccount` account on account.name = mpa.default_account
		where `tabMode of Payment`.enabled = 1 and mpa.company = %(company)s
			and account.company = %(company)s and account.account_type in ('Cash', 'Bank')
			and `tabMode of Payment`.name like %(txt)s {match_cond}
		order by `tabMode of Payment`.name
		limit %(start)s, %(page_len)s
		""".format(match_cond=get_match_cond("Mode of Payment")),
		{"company": company, "txt": f"%{txt}%", "start": start, "page_len": page_len},
	)


def expense_accounts(settings=None):
	settings = settings or get_settings()
	return {
		"office": setting_value(settings, "office_expense_account"),
		"meal": setting_value(settings, "meal_expense_account"),
		"travel": setting_value(settings, "travel_expense_account"),
		"other": setting_value(settings, "other_expense_account"),
	}


def setting_value(settings, fieldname):
	value = settings.get(fieldname)
	if value or settings.doctype == "Raven Accounting Settings":
		return value
	return get_settings().get(fieldname)


def get_company_cost_center(settings, company):
	if settings.get("cost_center"):
		return settings.cost_center
	defaults = get_settings()
	if defaults.company == company and defaults.cost_center:
		return defaults.cost_center
	return frappe.db.get_value("Company", company, "cost_center")


def resolve_account(company, configured_value):
	"""Resolve an account name or reusable account number for a company."""
	if not configured_value:
		return None
	if frappe.db.exists("Account", {"name": configured_value, "company": company, "is_group": 0}):
		return configured_value
	account_number = configured_value
	if frappe.db.exists("Account", configured_value):
		account_number = frappe.db.get_value("Account", configured_value, "account_number")
	matches = frappe.get_all(
		"Account",
		filters={"company": company, "account_number": account_number, "is_group": 0},
		pluck="name",
		limit=2,
	)
	if len(matches) > 1:
		frappe.throw(f"Account number {account_number} is duplicated in company {company}.")
	return matches[0] if matches else None


def ensure_bot_membership(settings=None, bot_name=None, channel=None):
	settings = settings or get_settings()
	bot_name = bot_name or settings.bot
	channel = channel or settings.channel
	bot_user = frappe.db.get_value("Raven Bot", bot_name, "raven_user")
	if not bot_user or not channel:
		return

	workspace = frappe.db.get_value("Raven Channel", channel, "workspace")
	if workspace and not frappe.db.exists(
		"Raven Workspace Member", {"workspace": workspace, "user": bot_user}
	):
		frappe.get_doc({
			"doctype": "Raven Workspace Member",
			"workspace": workspace,
			"user": bot_user,
		}).insert(ignore_permissions=True)

	if not frappe.db.exists(
		"Raven Channel Member", {"channel_id": channel, "user_id": bot_user}
	):
		frappe.get_doc({
			"doctype": "Raven Channel Member",
			"channel_id": channel,
			"user_id": bot_user,
		}).insert(ignore_permissions=True)
