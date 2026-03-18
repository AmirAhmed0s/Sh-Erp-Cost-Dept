# Copyright (c) 2024, Amir Mansi and contributors
# For license information, please see license.txt

"""
Advanced Inventory Dimension Report
=====================================
A dynamic, multi-dimensional inventory report that mirrors enterprise-grade
reporting tools (Dynamics 365 Finance style).

Dimensions can be toggled on/off:
  - Warehouse, Batch, Brand, Item Group

Multi-select filters:
  - Items, Warehouses, Brands, Batches

Date filtering:
  - As-of date  OR  from_date → to_date

Grouping is built dynamically based on the enabled dimension toggles.
Valuation is calculated per the specific Brand/Batch combination.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = _get_columns(filters)
	data = _get_data(filters)
	return columns, data


# -----------------------------------------------------------------------
# Column builder
# -----------------------------------------------------------------------

def _get_columns(filters):
	columns = [
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 140,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 180,
		},
	]

	if filters.get("show_item_group") == "Yes":
		columns.append(
			{
				"fieldname": "item_group",
				"label": _("Item Group"),
				"fieldtype": "Link",
				"options": "Item Group",
				"width": 120,
			}
		)

	if filters.get("show_warehouse") == "Yes":
		columns.append(
			{
				"fieldname": "warehouse",
				"label": _("Warehouse"),
				"fieldtype": "Link",
				"options": "Warehouse",
				"width": 140,
			}
		)

	if filters.get("show_batch") == "Yes":
		columns.append(
			{
				"fieldname": "batch_no",
				"label": _("Batch"),
				"fieldtype": "Link",
				"options": "Batch",
				"width": 120,
			}
		)

	if filters.get("show_brand") == "Yes":
		columns.append(
			{
				"fieldname": "brand",
				"label": _("Brand"),
				"fieldtype": "Link",
				"options": "Brand",
				"width": 120,
			}
		)

	columns += [
		{
			"fieldname": "qty_on_hand",
			"label": _("Qty On Hand"),
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname": "uom",
			"label": _("UOM"),
			"fieldtype": "Link",
			"options": "UOM",
			"width": 80,
		},
		{
			"fieldname": "valuation_rate",
			"label": _("Valuation Rate"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"fieldname": "stock_value",
			"label": _("Stock Value"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"fieldname": "age_days",
			"label": _("Age (Days)"),
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"fieldname": "first_entry_date",
			"label": _("First Entry Date"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "last_movement_date",
			"label": _("Last Movement Date"),
			"fieldtype": "Date",
			"width": 140,
		},
		{
			"fieldname": "last_movement_days",
			"label": _("Days Since Last Movement"),
			"fieldtype": "Int",
			"width": 160,
		},
	]

	return columns


# -----------------------------------------------------------------------
# Data query
# -----------------------------------------------------------------------

def _get_data(filters):
	conditions, params = _build_conditions(filters)
	group_by_fields = _build_group_by(filters)

	select_fields = _build_select_fields(filters)

	sql = f"""
		SELECT
			{select_fields}
		FROM
			`tabStock Ledger Entry` sle
			INNER JOIN `tabItem` i ON i.name = sle.item_code
		WHERE
			sle.is_cancelled = 0
			{conditions}
		GROUP BY
			{group_by_fields}
		HAVING
			SUM(sle.actual_qty) <> 0
		ORDER BY
			{group_by_fields}
	"""

	rows = frappe.db.sql(sql, params, as_dict=True)

	as_of_date = getdate(filters.get("as_of_date") or nowdate())
	for row in rows:
		row["stock_value"] = flt(row.get("qty_on_hand", 0)) * flt(row.get("valuation_rate", 0))
		if row.get("first_entry_date"):
			row["age_days"] = (as_of_date - getdate(row["first_entry_date"])).days
		else:
			row["age_days"] = 0
		if row.get("last_movement_date"):
			row["last_movement_days"] = (as_of_date - getdate(row["last_movement_date"])).days
		else:
			row["last_movement_days"] = 0

	return rows


def _build_select_fields(filters):
	fields = [
		"sle.item_code",
		"i.item_name",
		"i.stock_uom AS uom",
		"SUM(sle.actual_qty) AS qty_on_hand",
		# Quantity-weighted average valuation rate:
		# SUM(qty * rate) / NULLIF(SUM(qty), 0)
		# Uses only incoming entries (actual_qty > 0) to avoid skewing the
		# average with outgoing movements (which carry the rate at time of issue).
		"COALESCE("
		"  SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty * sle.valuation_rate ELSE 0 END)"
		"  / NULLIF(SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END), 0)"
		", 0) AS valuation_rate",
		"MIN(sle.posting_date) AS first_entry_date",
		"MAX(sle.posting_date) AS last_movement_date",
	]

	if filters.get("show_item_group") == "Yes":
		fields.append("i.item_group")
	if filters.get("show_warehouse") == "Yes":
		fields.append("sle.warehouse")
	if filters.get("show_batch") == "Yes":
		fields.append("sle.batch_no")
	if filters.get("show_brand") == "Yes":
		fields.append("sle.custom_item_brand AS brand")

	return ",\n\t\t\t".join(fields)


def _build_group_by(filters):
	# i.item_name and i.stock_uom are functionally dependent on sle.item_code in ERPNext,
	# but must be listed explicitly to satisfy ONLY_FULL_GROUP_BY mode.
	group_fields = ["sle.item_code", "i.item_name", "i.stock_uom"]

	if filters.get("show_item_group") == "Yes":
		group_fields.append("i.item_group")
	if filters.get("show_warehouse") == "Yes":
		group_fields.append("sle.warehouse")
	if filters.get("show_batch") == "Yes":
		group_fields.append("sle.batch_no")
	if filters.get("show_brand") == "Yes":
		group_fields.append("sle.custom_item_brand")

	return ", ".join(group_fields)


def _build_conditions(filters):
	conditions = ""
	params = {}

	# Date range
	as_of_date = filters.get("as_of_date")
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	if as_of_date:
		conditions += " AND sle.posting_date <= %(as_of_date)s"
		params["as_of_date"] = as_of_date
	elif from_date and to_date:
		conditions += " AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s"
		params["from_date"] = from_date
		params["to_date"] = to_date

	# Item filter (multi-select, comma-separated)
	items = _parse_multiselect(filters.get("items"))
	if items:
		conditions += " AND sle.item_code IN %(items)s"
		params["items"] = items

	# Warehouse filter
	warehouses = _parse_multiselect(filters.get("warehouses"))
	if warehouses:
		conditions += " AND sle.warehouse IN %(warehouses)s"
		params["warehouses"] = warehouses

	# Brand filter
	brands = _parse_multiselect(filters.get("brands"))
	if brands:
		conditions += " AND sle.custom_item_brand IN %(brands)s"
		params["brands"] = brands

	# Batch filter
	batches = _parse_multiselect(filters.get("batches"))
	if batches:
		conditions += " AND sle.batch_no IN %(batches)s"
		params["batches"] = batches

	# Company
	if filters.get("company"):
		conditions += " AND sle.company = %(company)s"
		params["company"] = filters.get("company")

	return conditions, params


def _parse_multiselect(value):
	"""
	Accepts a JSON list (from MultiSelectList filter), a comma-separated
	string, or None.  Always returns a tuple suitable for SQL IN clause.
	"""
	if not value:
		return None
	if isinstance(value, (list, tuple)):
		cleaned = [v for v in value if v]
		return tuple(cleaned) if cleaned else None
	if isinstance(value, str):
		cleaned = [v.strip() for v in value.split(",") if v.strip()]
		return tuple(cleaned) if cleaned else None
	return None


# -----------------------------------------------------------------------
# PDF generation helper  (called from client via frappe.call)
# -----------------------------------------------------------------------

@frappe.whitelist()
def generate_pdf_report(filters):
	"""
	Generate an aggregated PDF inventory report using Jinja2 template.
	Returns the raw HTML which the client can print/download via the browser.
	"""
	import json

	if isinstance(filters, str):
		filters = json.loads(filters)

	filters = frappe._dict(filters)
	_, data = execute(filters)

	template_path = (
		"sh_erp_cost_dept/inventory_management/report/"
		"advanced_inventory_dimension_report/aggregated_report.html"
	)

	context = frappe._dict(
		{
			"data": data,
			"filters": filters,
			"company": filters.get("company") or frappe.defaults.get_user_default("company"),
			"report_title": _("Advanced Inventory Dimension Report"),
			"show_warehouse": filters.get("show_warehouse") == "Yes",
			"show_batch": filters.get("show_batch") == "Yes",
			"show_brand": filters.get("show_brand") == "Yes",
			"show_item_group": filters.get("show_item_group") == "Yes",
		}
	)

	html = frappe.render_template(template_path, context)
	return html
