# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe

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
