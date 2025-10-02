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
