# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe.utils import flt
from pypika.terms import ExistsCriterion

from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport


def execute(filters=None):
	args = {
		"account_type": "Payable",
		"naming_by": ["Buying Settings", "supp_master_name"],
	}
	return CustomAccountsPayableReport(filters).run(args)


class CustomAccountsPayableReport(ReceivablePayableReport):
	def prepare_conditions(self):
		project = self.filters.pop("project", None)
		super().prepare_conditions()

		if project:
			self.filters.project = project
			self.add_project_filter(project)

	def add_project_filter(self, project):
		projects = list(project) if isinstance(project, (list, tuple, set)) else [project]
		gle = frappe.qb.DocType("GL Entry")
		matching_gl_entry = (
			frappe.qb.from_(gle)
			.select(gle.name)
			.where(
				(gle.company == self.ple.company)
				& (gle.account == self.ple.account)
				& (gle.voucher_type == self.ple.voucher_type)
				& (gle.voucher_no == self.ple.voucher_no)
				& (gle.party_type == self.ple.party_type)
				& (gle.party == self.ple.party)
				& (gle.project.isin(projects))
				& (gle.is_cancelled == 0)
			)
		)
		self.qb_selection_filter.append(ExistsCriterion(matching_gl_entry))

	def append_row(self, row):
		super().append_row(row)
		project = self.filters.get("project")
		if isinstance(project, str):
			row.project = project
		elif isinstance(project, (list, tuple, set)) and len(project) == 1:
			row.project = next(iter(project))

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
