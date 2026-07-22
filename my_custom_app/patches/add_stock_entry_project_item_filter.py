from my_custom_app.setup.install import get_custom_fields

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	custom_fields = get_custom_fields()
	create_custom_fields({"Stock Entry": custom_fields["Stock Entry"]}, ignore_validate=True)
