app_name = "my_custom_app"
app_title = "convert In word to Vietnamese"
app_publisher = "frappe"
app_description = "custom"
app_email = "frappe@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "my_custom_app",
# 		"logo": "/assets/my_custom_app/logo.png",
# 		"title": "convert In word to Vietnamese",
# 		"route": "/my_custom_app",
# 		"has_permission": "my_custom_app.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/my_custom_app/css/my_custom_app.css"
# app_include_js = "/assets/my_custom_app/js/my_custom_app.js"

# include js, css files in header of web template
# web_include_css = "/assets/my_custom_app/css/my_custom_app.css"
# web_include_js = "/assets/my_custom_app/js/my_custom_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "my_custom_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "my_custom_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "my_custom_app.utils.jinja_methods",
# 	"filters": "my_custom_app.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "my_custom_app.install.before_install"
# after_install = "my_custom_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "my_custom_app.uninstall.before_uninstall"
# after_uninstall = "my_custom_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "my_custom_app.utils.before_app_install"
# after_app_install = "my_custom_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "my_custom_app.utils.before_app_uninstall"
# after_app_uninstall = "my_custom_app.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "my_custom_app.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Sales Invoice": {
        "before_save": "my_custom_app.sales_invoice.before_save"
    },
    "Purchase Invoice": {
        "before_save": "my_custom_app.purchase_invoice.before_save"
    },
    "Salary Slip": {
        "before_save": "my_custom_app.salary_slip.before_save"
    } 
    # "*": {
    #     "on_update": "method",
    #     "on_cancel": "method",
    #     "on_trash": "method"
    # }
}
# Scheduled Tasks
# ---------------

scheduler_events = {
# 	"all": [
# 		"my_custom_app.tasks.all"
# 	],
	"daily": [
		"my_custom_app.scheduler.jobs.update_last_sync_of_checkin"
	],
# 	"hourly": [
# 		"my_custom_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"my_custom_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"my_custom_app.tasks.monthly"
# 	],
}

# Testing
# -------

# before_tests = "my_custom_app.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"erpnext.controllers.item_variant.create_variant": "my_custom_app.controllers.override.custom_create_variant",
	"erpnext.controllers.item_variant.enqueue_multiple_variant_creation": "my_custom_app.controllers.override.custom_enqueue_multiple_variant_creation",
    "hrms.hr.doctype.attendance.attendance.mark_bulk_attendance":"my_custom_app.controllers.attendance.mark_bulk_attendance",
	"hrms.hr.doctype.employee_attendance_tool.employee_attendance_tool.mark_employee_attendance":"my_custom_app.controllers.attendance.mark_employee_attendance"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "my_custom_app.task.get_dashboard_data"
# }
override_doctype_class = {
    "Payroll Entry": "my_custom_app.controllers.payroll_entry.CustomPayrollEntry",
	"Salary Slip": "my_custom_app.controllers.payroll_entry.CustomSalarySlip"
}
# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["my_custom_app.utils.before_request"]
# after_request = ["my_custom_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["my_custom_app.utils.before_job"]
# after_job = ["my_custom_app.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"my_custom_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

after_install = "my_custom_app.setup.install.after_install"

doctype_js = {
    "Employee Attendance Tool" : "public/js/my.js"
    }
fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=","convert In word to Vietnamese"]]},

	{"dt": "Property Setter", "filters": [["module", "=","convert In word to Vietnamese"]]},

	{"dt": "DocType", "filters": [["module", "=","convert In word to Vietnamese"]]},

    {"dt": "Client Script", "filters": [["module", "=","convert In word to Vietnamese"]]},

    {"dt": "Server Script", "filters": [["module", "=","convert In word to Vietnamese"]]}
]