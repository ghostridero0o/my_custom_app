import frappe
from erpnext.stock.doctype.item.item import create_variant as original_create_variant

def create_variant(item_template, args):
    """Custom Create Variant Function"""
    variant = original_create_variant(item_template, args)  # G?i hàm g?c c?a ERPNext
    update_variant_name(variant)  # C?p nh?t tên variant theo attributes
    return variant

def update_variant_name(item):
    """T?o tên Item Variant d?a trên Attribute Values"""
    if item.variant_of and item.attributes:
        attributes = [attr.attribute_value for attr in item.attributes if attr.attribute_value]
        if attributes:
            new_name = "-".join(attributes)
            frappe.db.set_value("Item", item.name, {
                "item_name": new_name,
                "item_code": new_name
            })
            frappe.db.commit()
