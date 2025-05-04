from frappe import msgprint
import frappe
import datetime
import json
from frappe import _
from frappe.utils import cstr
from frappe.model.document import Document
from frappe.utils import get_datetime
from frappe.utils import getdate

@frappe.whitelist()
def mark_bulk_attendance(data):
    import json
    

    # Nếu dữ liệu là chuỗi JSON, chuyển nó thành dictionary
    if isinstance(data, str):
        data = json.loads(data)
    
    # Chuyển dữ liệu thành dict để truy cập dễ dàng hơn
    data = frappe._dict(data)
    
    # Kiểm tra nếu không có ngày nào chưa được chấm công
    if not data.unmarked_days:
        frappe.throw(_("Please select a date."))
        return

    # Lặp qua tất cả các ngày chưa được chấm công
    for date in data.unmarked_days:
        # Tạo dictionary cho bản ghi Attendance mới
        doc_dict = {
            "doctype": "Attendance",
            "employee": data.employee,
            "attendance_date": get_datetime(date),
            "status": data.status,
            "custom_project": data.custom_project,  # Thêm trường custom_project vào đây
        }

        # Tạo bản ghi mới và lưu
        attendance = frappe.get_doc(doc_dict).insert()
        
        # Submit bản ghi attendance
        attendance.submit()

@frappe.whitelist()
def mark_employee_attendance(
    employee_list: list | str,
    status: str,
    date: str | datetime.date,
    leave_type: str | None = None,
    company: str | None = None,
    late_entry: int | None = None,
    early_exit: int | None = None,
    shift: str | None = None,
    project: str | None = None,  # Thêm trường project vào tham số
) -> None:
    if isinstance(employee_list, str):
        employee_list = json.loads(employee_list)
    frappe.msgprint("HELLO")

    for employee in employee_list:
        leave_type = None
        if status == "On Leave" and leave_type:
            leave_type = leave_type
        

        # Tạo bản ghi Attendance và thêm trường custom_project
        attendance = frappe.get_doc(
            dict(
                doctype="Attendance",
                employee=employee,
                attendance_date=getdate(date),
                status=status,
                leave_type=leave_type,
                late_entry=late_entry,
                early_exit=early_exit,
                shift=shift,
                custom_project=project,  # Lưu giá trị vào trường custom_project
            )
        )

        # Lưu và submit bản ghi attendance
        attendance.insert()
        attendance.submit()



