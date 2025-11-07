import frappe
import frappe.www.list
from frappe import _


no_cache = 1

def get_context(context):
    # Lấy danh sách Task (bỏ status Template, Cancelled, Completed)
    tasks = frappe.get_all(
        "Task",
        fields=["name", "subject", "status", "exp_end_date", "modified", "owner"],
        filters={"status": ["not in", ["Template", "Cancelled", "Completed"]]},
        order_by="exp_end_date asc",
        limit_page_length=20
    )
    context.no_cache = 1

    context.tasks = tasks
    
    # Bật sidebar ERPNext
    context.show_sidebar = True
    
    # Tùy chọn: Thêm custom sidebar items
    context.sidebar_items = [
        {
            "label": "Bàn làm việc",
            "route": "/app",
            "icon": "user"
        },
        {
            "label": "Bảng chi tiết công việc",
            "route": "/app/task",
            "icon": "list"
        },
        
        {
            "label": "Dự án",
            "route": "/project",
            "icon": "folder"
        },
        {
            "label": "Văn bản nội bộ",
            "route": "/wiki",
            "icon": "folder"
        }
    ]
    
    return context