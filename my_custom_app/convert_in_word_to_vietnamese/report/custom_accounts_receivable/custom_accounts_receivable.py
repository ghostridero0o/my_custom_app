# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport


def execute(filters=None):
	args = {
		"account_type": "Receivable",
		"naming_by": ["Selling Settings", "cust_master_name"],
	}
	return CustomAccountsReceivableReport(filters).run(args)


class CustomAccountsReceivableReport(ReceivablePayableReport):
	def get_columns(self):
		super().get_columns()

		reverse_payment_column = {
			"label": _("Reverse Payment"),
			"fieldname": "reverse_payment",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		}

		paid_column_index = next(
			(index for index, column in enumerate(self.columns) if column.get("fieldname") == "paid"),
			None,
		)
		if paid_column_index is None:
			self.columns.append(reverse_payment_column)
		else:
			self.columns.insert(paid_column_index, reverse_payment_column)

	def prepare_conditions(self):
		super().prepare_conditions()
		self.add_project_filter()

	def get_currency_fields(self):
		return super().get_currency_fields() + ["reverse_payment"]

	def has_ledger_activity(self, row):
		precision = self.currency_precision
		threshold = 1.0 / 10**precision
		amount_fields = (
			"invoiced",
			"paid",
			"credit_note",
			"outstanding",
			"invoiced_in_account_currency",
			"paid_in_account_currency",
			"credit_note_in_account_currency",
			"outstanding_in_account_currency",
		)
		return any(abs(flt(row.get(field))) >= threshold for field in amount_fields)

	def has_outstanding_amount(self, row):
		threshold = 1.0 / 10**self.currency_precision
		return (abs(flt(row.outstanding)) >= threshold) and (
			(abs(flt(row.outstanding_in_account_currency)) >= threshold)
			or (row.voucher_no in self.err_journals)
		)

	def build_data(self):
		hide_reconciled_entries = self.filters.get("hide_reconciled_entries")

		for _key, row in self.voucher_balance.items():
			row.outstanding = flt(row.invoiced - row.paid - row.credit_note, self.currency_precision)
			row.outstanding_in_account_currency = flt(
				row.invoiced_in_account_currency
				- row.paid_in_account_currency
				- row.credit_note_in_account_currency,
				self.currency_precision,
			)
			row.invoice_grand_total = row.invoiced

			if not self.has_ledger_activity(row):
				continue

			self.set_reverse_payment_amount(row)

			if hide_reconciled_entries and not self.has_outstanding_amount(row):
				continue

			if self.is_invoice(row) and self.filters.based_on_payment_terms:
				self.allocate_outstanding_based_on_payment_terms(row)

				if row.payment_terms:
					for d in row.payment_terms:
						if hide_reconciled_entries and not self.has_outstanding_amount(d):
							continue
						if self.has_ledger_activity(d):
							self.append_row(d)

					self.allocate_extra_payments_or_credits(row)
				else:
					self.append_row(row)
			else:
				self.append_row(row)

		if self.filters.get("group_by_party"):
			self.append_subtotal_row(self.previous_party)
			if self.data:
				self.data.append(self.total_row_map.get("Total", {}))

	def set_reverse_payment_amount(self, row):
		row.reverse_payment = 0

		if row.voucher_type != "Payment Entry" or row.party_type != "Customer":
			return

		payment_type = frappe.get_cached_value("Payment Entry", row.voucher_no, "payment_type")
		if payment_type != "Pay":
			return

		# Reverse payment for a customer can appear as a positive receivable movement and
		# land in Invoiced Amount in the base report. Reclassify it into its own column.
		row.reverse_payment = row.invoiced
		row.invoiced = 0
		row.invoiced_in_account_currency = 0

	def add_project_filter(self):
		project = self.filters.get("project")
		if not project:
			return

		if isinstance(project, (list, tuple, set)):
			projects = list(project)
		else:
			projects = [project]

		invoices = frappe.get_list(
			"Sales Invoice",
			filters={
				"project": ("in", projects),
				"posting_date": ("<=", self.filters.report_date),
				"company": self.filters.company,
				"docstatus": 1,
			},
			pluck="name",
		)

		if not invoices:
			self.qb_selection_filter.append(self.ple.name.isnull())
			return

		self.qb_selection_filter.append(
			((self.ple.voucher_type == "Sales Invoice") & (self.ple.voucher_no.isin(invoices)))
			| (
				(self.ple.against_voucher_type == "Sales Invoice")
				& (self.ple.against_voucher_no.isin(invoices))
			)
		)
