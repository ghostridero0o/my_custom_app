import frappe
from frappe import _
from frappe.model.document import Document

from my_custom_app.convert_in_word_to_vietnamese.report.bclc_tt_tt99_gt.bclc_tt_tt99_gt import (
	CASH_PREFIXES,
	ROWS,
)


class BCLCTTGTSettings(Document):
	def validate(self):
		default_methods = {
			row["code"]: get_calculation_method(row.get("computed"))
			for row in ROWS
			if row and row.get("code") and row.get("computed")
		}
		for rule in self.account_rules:
			if not rule.calculation_method:
				rule.calculation_method = default_methods.get(rule.cash_flow_code)


@frappe.whitelist()
def reset_default_settings():
	settings = frappe.get_single("BCLC TT GT Settings")
	apply_default_settings(settings)
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	return _("BCLC TT GT Settings reset to default mapping")


def seed_default_settings_if_empty():
	if not frappe.db.exists("DocType", "BCLC TT GT Settings"):
		return

	settings = frappe.get_single("BCLC TT GT Settings")
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

	for row in ROWS:
		if not row or not row.get("code") or row.get("total") or row.get("computed") in ("opening", "exchange", "closing"):
			continue

		settings.append(
			"account_rules",
			{
				"enabled": 1,
				"cash_flow_code": row["code"],
				"calculation_method": get_calculation_method(row.get("computed")),
				"direction": "Inflow" if row.get("direction") == "inflow" else "Outflow" if row.get("direction") == "outflow" else "",
				"change_sign": "Debit - Credit" if row.get("change_sign") == "closing_minus_opening" else "Credit - Debit" if row.get("change_sign") == "opening_minus_closing" else "",
				"account_prefix": ", ".join(row.get("prefixes") or []),
				"exclude_account_prefix": ", ".join(row.get("exclude_prefixes") or []),
				"name_keywords": ", ".join(row.get("name_keywords") or []),
				"exclude_name_keywords": ", ".join(row.get("exclude_name_keywords") or []),
				"priority": 100,
				"description": row.get("label"),
			},
		)


def get_calculation_method(computed):
	return {
		"profit_before_tax": "Profit Before Tax",
		"depreciation": "Depreciation",
		"balance_change": "Balance Change",
		"period_activity": "Period Activity",
		"credit_activity": "Account Movement",
		"debit_activity": "Account Movement",
		"fx_unrealized": "FX Unrealized",
		"investment_finance_gain_loss": "Investment/Finance Gain Loss",
		"borrowing_cost": "Borrowing Cost",
		"asset_purchase_balance_change": "Period Activity",
		"account_movement": "Account Movement",
		"cash_filtered_account_activity": "Cash Filtered Account Activity",
		"cash_linked_credit_activity": "Cash Flow",
		"cash_linked_debit_activity": "Cash Flow",
		"cash_flow": "Cash Flow",
	}.get(computed, "")
