import frappe
from frappe.utils import add_days, nowdate
from collections import defaultdict


def send_attendance_list():
    # Lấy ngày hôm qua
    yesterday = add_days(nowdate(), -1)
    valid_statuses = ["Present", "Half Day", "Work From Home"]

    # Lấy dữ liệu cấu hình bot + channel_name
    settings = frappe.get_single("Attendance Notification Settings")
    bot_name = settings.raven_bot or "Content Bot"
    channel_name = settings.raven_channel  # now assumed to be channel_name (e.g. "test")

    # Resolve channel_id from channel_name
    channel_id = channel_name
    # Lấy các bản ghi đã Submit của ngày hôm qua
    records = frappe.get_all(
        "Attendance",
        filters={
            "attendance_date": yesterday,
            "status": ["in", valid_statuses],
            "docstatus": 1
        },
        fields=["employee", "employee_name", "status", "department", "shift"]
    )

    if not records:
        return

    # Mapping trạng thái tiếng Việt
    status_map = {
        "Present": "Làm đủ ca",
        "Half Day": "Làm nửa ca",
        "Work From Home": "Làm tại nhà"
    }

    # Nhóm theo phòng ban
    grouped = defaultdict(list)
    for rec in records:
        dept = rec.department or "Không xác định"
        grouped[dept].append(rec)

    # Tạo nội dung message markdown
    message_lines = [f"📅 **Ngày:** {frappe.format_value(yesterday, {'fieldtype': 'Date'})}", ""]
    message_lines.append("👥 **Danh sách công nhân viên đi làm:**")

    for dept, emp_list in grouped.items():
        message_lines.append(f"\n### 🏢 {dept}")
        for emp in emp_list:
            # Gán status hiển thị
            if emp.shift == "Ca đêm":
                display_status = "Tăng ca đêm"
            else:
                display_status = status_map.get(emp.status, emp.status)

            message_lines.append(f"- {emp.employee_name or emp.employee} (`{emp.employee}`) - *{display_status}*")

    message = "\n".join(message_lines)

    # Gửi message bằng Raven Bot
    bot = frappe.get_doc("Raven Bot", bot_name)
    bot.send_message(
        channel_id=channel_id,
        text=message,
        markdown=True
    )
