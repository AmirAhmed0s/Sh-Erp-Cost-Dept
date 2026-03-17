# Copyright (c) 2024, Amir Mansi and contributors
# For license information, please see license.txt

"""
Item Brand & UOM Validation — Server-Side Module
=================================================
Provides server-side validation for Brand and UOM integrity across all
supported transaction DocTypes.

Functions
---------
validate_brand_uom(doc, method)
    Hook for: Sales Order, Purchase Order, Delivery Note, Stock Entry,
              BOM, Material Request.
    Validates that each row's ``custom_item_brand`` is an allowed brand
    for the selected ``item_code``.

validate_work_order_brand(doc, method)
    Hook for: Work Order.
    Runs the standard brand/UOM check AND verifies that the brands on
    required items are consistent with the source BOM (BOM → Work Order
    cross-document consistency).
"""

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_allowed_brands(item_code):
	"""
	Return the list of brand names defined in item.custom_brands.
	Uses ``frappe.get_cached_doc`` so repeated calls within a single
	request hit the document cache, not the database.
	"""
	try:
		item_doc = frappe.get_cached_doc("Item", item_code)
		custom_brands = getattr(item_doc, "custom_brands", None) or []
		return [
			getattr(d, "brand", None)
			for d in custom_brands
			if getattr(d, "brand", None)
		]
	except Exception:
		return []


def _get_allowed_uoms(item_code):
	"""
	Return all UOM names allowed for an item:
	  • Stock UOM
	  • All UOMs listed in the item's UOM Conversion Detail table
	"""
	try:
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or ""
		uom_rows = frappe.get_all(
			"UOM Conversion Detail",
			filters={"parent": item_code, "parenttype": "Item"},
			fields=["uom"],
			order_by=None,
		)
		allowed = [stock_uom] if stock_uom else []
		for u in uom_rows:
			if u.uom and u.uom not in allowed:
				allowed.append(u.uom)
		return allowed
	except Exception:
		return []


def _get_items_table(doctype):
	"""Return the items child-table fieldname for a given DocType."""
	return {
		"Sales Order": "items",
		"Purchase Order": "items",
		"Delivery Note": "items",
		"Material Request": "items",
		"BOM": "items",
		"Work Order": "required_items",
		"Stock Entry": "items",
	}.get(doctype, "items")


# ---------------------------------------------------------------------------
# Public hooks
# ---------------------------------------------------------------------------


def validate_brand_uom(doc, method=None):
	"""
	Hook: validate — Sales Order, Purchase Order, Delivery Note,
	                 Stock Entry, BOM, Material Request.

	For each item row that has ``custom_item_brand`` set, verify that the
	selected brand is in the item's allowed brand list.

	If the item has no brands defined the validation is skipped
	(permissive default — brands are optional).
	"""
	table_field = _get_items_table(doc.doctype)
	rows = getattr(doc, table_field, []) or []

	for idx, row in enumerate(rows, start=1):
		item_code = getattr(row, "item_code", None)
		if not item_code:
			continue

		brand = getattr(row, "custom_item_brand", None)
		if brand:
			allowed_brands = _get_allowed_brands(item_code)

			# Only enforce if the item actually defines brands
			if allowed_brands and brand not in allowed_brands:
				frappe.throw(
					_(
						"Row {0}: Brand <b>{1}</b> is not allowed for item <b>{2}</b>. "
						"Please select a valid brand."
					).format(idx, brand, item_code),
					title=_("Invalid Item Brand"),
				)

		# UOM validation — only enforce if the item defines UOMs
		uom = getattr(row, "uom", None) or getattr(row, "stock_uom", None)
		if uom:
			allowed_uoms = _get_allowed_uoms(item_code)
			if allowed_uoms and uom not in allowed_uoms:
				frappe.throw(
					_(
						"Row {0}: UOM <b>{1}</b> is not allowed for item <b>{2}</b>. "
						"Please select a valid UOM."
					).format(idx, uom, item_code),
					title=_("Invalid UOM"),
				)


def validate_work_order_brand(doc, method=None):
	"""
	Hook: validate — Work Order.

	1. Runs the standard brand check on required_items.
	2. Cross-document consistency: when a Work Order is created from a
	   BOM, verifies that each required item's brand matches the brand
	   recorded on the corresponding BOM item row (if any).

	This enforces the BOM → Work Order → Stock Entry brand chain.
	"""
	# Step 1: standard brand validation
	validate_brand_uom(doc, method)

	# Step 2: cross-document BOM consistency
	if not doc.bom_no:
		return

	bom_items = frappe.get_all(
		"BOM Item",
		filters={"parent": doc.bom_no},
		fields=["item_code", "custom_item_brand"],
		order_by=None,
	)

	# Map item_code → brand from the BOM (only where a brand is set)
	bom_brand_map = {
		b.item_code: b.custom_item_brand
		for b in bom_items
		if b.get("custom_item_brand")
	}

	if not bom_brand_map:
		return  # No brand restrictions in BOM — nothing more to check

	for idx, row in enumerate(doc.required_items or [], start=1):
		wo_brand = getattr(row, "custom_item_brand", None)
		bom_brand = bom_brand_map.get(row.item_code)

		if bom_brand and wo_brand and wo_brand != bom_brand:
			frappe.throw(
				_(
					"Row {0}: Brand <b>{1}</b> for item <b>{2}</b> does not match "
					"the BOM brand <b>{3}</b> (BOM: {4}). "
					"Please keep brands consistent across the manufacturing chain."
				).format(
					idx,
					wo_brand,
					row.item_code,
					bom_brand,
					doc.bom_no,
				),
				title=_("Brand Mismatch with BOM"),
			)
