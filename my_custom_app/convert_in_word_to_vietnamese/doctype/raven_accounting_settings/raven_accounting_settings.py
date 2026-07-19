import frappe
from frappe import _
from frappe.model.document import Document

from my_custom_app.raven.settings import ensure_bot_membership


class RavenAccountingSettings(Document):
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
