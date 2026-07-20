import frappe
from frappe import _
from frappe.model.document import Document

from my_custom_app.raven.settings import ensure_bot_membership


class RavenAccountingSettings(Document):
	def before_validate(self):
		account_fields = (
			"cash_account", "office_expense_account", "meal_expense_account",
			"travel_expense_account", "other_expense_account",
			"journal_debit_account", "journal_credit_account",
		)
		for row in [self, *self.channel_configurations]:
			for fieldname in account_fields:
				value = row.get(fieldname)
				if value and frappe.db.exists("Account", value):
					row.set(fieldname, frappe.db.get_value("Account", value, "account_number") or value)

	def validate(self):
		if not self.enabled:
			return
		channels = [row.channel for row in self.channel_configurations if row.channel]
		if len(channels) != len(set(channels)):
			frappe.throw(_("Each Raven Channel can only have one accounting configuration."))
		for bot in {self.bot, *(row.bot for row in self.channel_configurations if row.bot)}:
			bot_user = frappe.db.get_value("Raven Bot", bot, "raven_user")
			if not bot_user or not frappe.db.exists("Raven User", {"name": bot_user, "enabled": 1}):
				frappe.throw(_("Raven Bot {0} must have an enabled Raven User.").format(bot))

	def on_update(self):
		if self.enabled:
			ensure_bot_membership(self)
			for row in self.channel_configurations:
				ensure_bot_membership(self, row.bot or self.bot, row.channel)
