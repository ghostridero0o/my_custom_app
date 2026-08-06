import frappe
from employee_self_service.employee_self_service.doctype.petty_expense.petty_expense import PettyExpense

class CustomPettyExpense(PettyExpense):
    def on_cancel(self):
        """Override on_cancel để không throw mà hủy luôn Journal Entry"""
        if self.journal_entry:
            try:
                je = frappe.get_doc("Journal Entry", self.journal_entry)
                if je.docstatus == 1:
                    je.cancel()
                # Clear link
                frappe.db.set_value("Petty Expense", self.name, "journal_entry", None)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "CustomPettyExpense Cancel Error")
    def make_journal_entry(self):
        jv_doc = frappe.new_doc("Journal Entry")
        jv_doc.entry_type = "Journal Entry"
        jv_doc.company = self.company
        jv_doc.posting_date = self.date
        # Journal Entry V16 no longer uses the hidden header-level
        # ``user_remark`` to build the visible Remark. Mark this as a custom
        # remark so ERPNext does not regenerate/overwrite it during submit.
        jv_doc.custom_remark = 1
        jv_doc.remark = self.description or f"Chi phí lặt vặt: {self.name}"

        # Dòng debit
        jv_doc.append(
            "accounts",
            dict(
                account=self.expense_account,
                debit_in_account_currency=self.amount,
                cost_center=self.cost_center,
                project=self.custom_project,  # thêm custom_project
            ),
        )

        # Dòng credit
        jv_doc.append(
            "accounts",
            dict(
                account=self.payment_account,
                credit_in_account_currency=self.amount,
                cost_center=self.cost_center,
                project=self.custom_project,  # thêm custom_project
            ),
        )        

        # Submit và link lại
        jv_doc = jv_doc.submit()
        frappe.db.set_value(self.doctype, self.name, "journal_entry", jv_doc.name)
