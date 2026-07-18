# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe.utils import flt

from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport


def execute(filters=None):
	args = {
		"account_type": "Payable",
		"naming_by": ["Buying Settings", "supp_master_name"],
	}
	return CustomAccountsPayableReport(filters).run(args)


class CustomAccountsPayableReport(ReceivablePayableReport):
	def prepare_conditions(self):
		super().prepare_conditions()
		self.add_project_filter()

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

	def add_project_filter(self):
		project = self.filters.get("project")
		if not project:
			return

		if isinstance(project, (list, tuple, set)):
			projects = list(project)
		else:
			projects = [project]

		invoices = frappe.get_list(
			"Purchase Invoice",
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
			((self.ple.voucher_type == "Purchase Invoice") & (self.ple.voucher_no.isin(invoices)))
			| (
				(self.ple.against_voucher_type == "Purchase Invoice")
				& (self.ple.against_voucher_no.isin(invoices))
			)
		)
