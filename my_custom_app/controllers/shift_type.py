from hrms.hr.doctype.shift_type.shift_type import ShiftType
import frappe

class CustomShiftType(ShiftType):
    def mark_absent_for_dates_with_no_attendance(self, employee: str):
        # Override để bỏ qua auto mark absent
        frappe.logger().info(f"[CustomShiftType] Skipped auto absent for {employee}")
        return
