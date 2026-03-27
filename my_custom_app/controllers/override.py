import frappe
import json
from frappe import _
from frappe.utils import cstr

from erpnext.controllers.item_variant import copy_attributes_to_variant
from erpnext.controllers.item_variant import generate_keyed_value_combinations
from erpnext.controllers.item_variant import get_variant

@frappe.whitelist()
def custom_create_variant(item, args, use_template_image=False):
	use_template_image = frappe.parse_json(use_template_image)
	if isinstance(args, str):
		args = json.loads(args)

	template = frappe.get_doc("Item", item)
	variant = frappe.new_doc("Item")
	variant.variant_based_on = "Item Attribute"
	variant_attributes = []

	for d in template.attributes:
		variant_attributes.append({"attribute": d.attribute, "attribute_value": args.get(d.attribute)})

	variant.set("attributes", variant_attributes)
	copy_attributes_to_variant(template, variant)

	if use_template_image and template.image:
		variant.image = template.image

	make_variant_item_code(template.item_code, template.item_name, variant)

	return variant

def make_variant_item_code(template_item_code, template_item_name, variant):
	"""Uses template's item code and abbreviations to make variant's item code"""
	if variant.item_code:
		return

	abbreviations = []
	for attr in variant.attributes:
		item_attribute = frappe.db.sql(
			"""select i.numeric_values, v.abbr
			from `tabItem Attribute` i left join `tabItem Attribute Value` v
				on (i.name=v.parent)
			where i.name=%(attribute)s and (v.attribute_value=%(attribute_value)s or i.numeric_values = 1)""",
			{"attribute": attr.attribute, "attribute_value": attr.attribute_value},
			as_dict=True,
		)

		if not item_attribute:
			continue
			# frappe.throw(_('Invalid attribute {0} {1}').format(frappe.bold(attr.attribute),
			# 	frappe.bold(attr.attribute_value)), title=_('Invalid Attribute'),
			# 	exc=InvalidItemAttributeValueError)

		abbr_or_value = (
			cstr(attr.attribute_value) if item_attribute[0].numeric_values else item_attribute[0].abbr
		)
		abbreviations.append(abbr_or_value)

	if abbreviations:
		variant.item_code = merge_template_with_attributes(template_item_code, abbreviations)
		variant.item_name = merge_template_with_attributes(template_item_name, abbreviations)


def merge_template_with_attributes(template_value, abbreviations):
	if not abbreviations:
		return template_value

	template_value = cstr(template_value).strip()
	parts = [cstr(value).strip() for value in abbreviations if cstr(value).strip()]

	if not template_value:
		return " ".join(parts)

	if parts and starts_with_same_words(parts[0], template_value):
		return " ".join(parts)

	return " ".join([template_value] + parts)


def starts_with_same_words(value, prefix):
	value_words = cstr(value).strip().lower().split()
	prefix_words = cstr(prefix).strip().lower().split()

	if not value_words or not prefix_words:
		return False

	return value_words[: len(prefix_words)] == prefix_words

@frappe.whitelist()
def custom_enqueue_multiple_variant_creation(item, args, use_template_image=False):
	use_template_image = frappe.parse_json(use_template_image)
	# There can be innumerable attribute combinations, enqueue
	if isinstance(args, str):
		variants = json.loads(args)
	else:
		variants = args
	total_variants = 1
	for key in variants:
		total_variants *= len(variants[key])
	if total_variants >= 600:
		frappe.throw(_("Please do not create more than 500 items at a time"))
		return
	if total_variants < 10:
		return create_multiple_variants(item, args, use_template_image)
	else:
		frappe.enqueue(
			"my_custom_app.my_custom_app.controllers.override.create_multiple_variants",
			item=item,
			args=args,
			use_template_image=use_template_image,
			now=frappe.flags.in_test,
		)
		return "queued"


def create_multiple_variants(item, args, use_template_image=False):
	count = 0
	if isinstance(args, str):
		args = json.loads(args)

	template_item = frappe.get_doc("Item", item)
	args_set = generate_keyed_value_combinations(args)

	for attribute_values in args_set:
		if not get_variant(item, args=attribute_values):
			variant = custom_create_variant(item, attribute_values)
			if use_template_image and template_item.image:
				variant.image = template_item.image
			variant.save()
			count += 1

	return count
