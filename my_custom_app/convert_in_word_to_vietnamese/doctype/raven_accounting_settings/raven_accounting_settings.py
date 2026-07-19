import frappe
from frappe import _
from frappe.model.document import Document

from my_custom_app.raven.settings import ensure_bot_membership


class RavenAccountingSettings(Document):
	def validate(self):
		if not self.enabled:
			return
		bot_user = frappe.db.get_value("Raven Bot", self.bot, "raven_user")
		if not bot_user or not frappe.db.exists("Raven User", {"name": bot_user, "enabled": 1}):
			frappe.throw(_("The selected Raven Bot must have an enabled Raven User."))

	def on_update(self):
		if self.enabled:
			ensure_bot_membership(self)
