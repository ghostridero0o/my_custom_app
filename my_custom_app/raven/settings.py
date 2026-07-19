import frappe


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


def expense_accounts(settings=None):
	settings = settings or get_settings()
	return {
		"office": settings.office_expense_account,
		"meal": settings.meal_expense_account,
		"travel": settings.travel_expense_account,
		"other": settings.other_expense_account,
	}


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
