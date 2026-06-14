import frappe
from frappe import _
from frappe.model.document import Document

from my_custom_app.convert_in_word_to_vietnamese.report.bclc_tt_tt99_tt.bclc_tt_tt99_tt import (
	CASH_PREFIXES,
	DEFAULT_MAPPING_RULES,
)


class BCLCTTSettings(Document):
	pass


@frappe.whitelist()
def reset_default_settings():
	settings = frappe.get_single("BCLC TT Settings")
	apply_default_settings(settings)
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	return _("BCLC TT Settings reset to default mapping")


def seed_default_settings_if_empty():
	if not frappe.db.exists("DocType", "BCLC TT Settings"):
		return

	settings = frappe.get_single("BCLC TT Settings")
	if settings.cash_accounts or settings.account_rules:
		return

	apply_default_settings(settings)
	settings.save(ignore_permissions=True)


def apply_default_settings(settings):
	settings.enabled = 1
	settings.enable_custom_mapping = 1
	settings.set("cash_accounts", [])
	settings.set("account_rules", [])

	for prefix in CASH_PREFIXES:
		settings.append(
			"cash_accounts",
			{
				"enabled": 1,
				"account_prefix": prefix,
				"description": f"Cash account prefix {prefix}",
			},
		)

	for rule in DEFAULT_MAPPING_RULES:
		settings.append(
			"account_rules",
			{
				"enabled": 1,
				"cash_flow_code": rule["code"],
				"direction": "Inflow" if rule["direction"] == "inflow" else "Outflow",
				"account_prefix": ", ".join(rule.get("prefixes") or []),
				"exclude_account_prefix": ", ".join(rule.get("exclude_prefixes") or []),
				"voucher_keywords": ", ".join(rule.get("keywords") or []),
				"priority": rule.get("priority", 100),
			},
		)
