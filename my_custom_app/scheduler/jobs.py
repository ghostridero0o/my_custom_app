import frappe
from frappe.utils import get_datetime, nowdate
import datetime

def update_last_sync_of_checkin():
    try:
        # L?y t?t c? các b?n ghi trong doctype Shift Type
        shift_types = frappe.get_all('Shift Type', fields=['name'])

        # L?y ngày hi?n t?i và chuy?n thành datetime, sau dó d?t gi? thành 23:00:00
        current_time = get_datetime(nowdate()).replace(hour=23, minute=0, second=0, microsecond=0)

        # C?p nh?t tru?ng 'last_sync_of_checkin' cho t?t c? các b?n ghi
        for shift in shift_types:
            frappe.db.set_value('Shift Type', shift['name'], 'last_sync_of_checkin', current_time)

        # Commit các thay d?i
        frappe.db.commit()

    except Exception as e:
        # N?u có l?i x?y ra, ghi l?i l?i vào log
        frappe.log_error(f"Error in update_last_sync_of_checkin: {str(e)}", "Scheduled Job Error")
