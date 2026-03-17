# Copyright (c) 2024, Amir Mansi and contributors
# For license information, please see license.txt

"""
Material Consumption Report
============================
Compares planned vs actual material usage for Work Orders:
  • Planned qty – required_qty from Work Order Item
  • Actual qty  – consumed_qty from Work Order Item
  • Variance    – actual minus planned
  • Wastage %   – variance as a percentage of planned

KPI summary: Total Items, Total Planned, Total Consumed, Total Wastage.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = _get_columns()
	data = _get_data(filters)
	report_summary = _get_report_summary(data)
	return columns, data, None, None, report_summary


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------


def _get_columns():
	return [
		{
			"fieldname": "work_order",
			"label": _("Work Order"),
			"fieldtype": "Link",
			"options": "Work Order",
			"width": 160,
		},
		{
			"fieldname": "production_item",
			"label": _("Production Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"fieldname": "item_code",
			"label": _("Material Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"fieldname": "item_name",
			"label": _("Material Name"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "uom",
			"label": _("UOM"),
			"fieldtype": "Link",
			"options": "UOM",
			"width": 80,
		},
		{
			"fieldname": "planned_qty",
			"label": _("Planned Qty"),
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"fieldname": "actual_qty",
			"label": _("Actual Qty"),
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"fieldname": "variance_qty",
			"label": _("Variance"),
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"fieldname": "wastage_pct",
			"label": _("Wastage %"),
			"fieldtype": "Percent",
			"width": 110,
		},
		{
			"fieldname": "wo_status",
			"label": _("WO Status"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "planned_start_date",
			"label": _("WO Start"),
			"fieldtype": "Date",
			"width": 120,
		},
	]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def _get_data(filters):
	conditions, params = _build_conditions(filters)

	sql = f"""
		SELECT
			wo.name                   AS work_order,
			wo.production_item,
			woi.item_code,
			woi.item_name,
			woi.stock_uom             AS uom,
			woi.required_qty          AS planned_qty,
			woi.consumed_qty          AS actual_qty,
			wo.status                 AS wo_status,
			wo.planned_start_date
		FROM
			`tabWork Order Item` woi
			INNER JOIN `tabWork Order` wo ON wo.name = woi.parent
		WHERE
			wo.docstatus = 1
			{conditions}
		ORDER BY
			wo.name,
			woi.item_code
	"""

	rows = frappe.db.sql(sql, params, as_dict=True)

	for row in rows:
		planned = flt(row.get("planned_qty"))
		actual = flt(row.get("actual_qty"))
		row["variance_qty"] = actual - planned
		row["wastage_pct"] = (
			((actual - planned) / planned * 100) if planned and actual > planned else 0.0
		)

	return rows


def _build_conditions(filters):
	conditions = ""
	params = {}

	if filters.get("company"):
		conditions += " AND wo.company = %(company)s"
		params["company"] = filters.company

	if filters.get("from_date"):
		conditions += " AND wo.planned_start_date >= %(from_date)s"
		params["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions += " AND wo.planned_start_date <= %(to_date)s"
		params["to_date"] = filters.to_date

	if filters.get("work_order"):
		conditions += " AND wo.name = %(work_order)s"
		params["work_order"] = filters.work_order

	if filters.get("production_item"):
		conditions += " AND wo.production_item = %(production_item)s"
		params["production_item"] = filters.production_item

	if filters.get("item_code"):
		conditions += " AND woi.item_code = %(item_code)s"
		params["item_code"] = filters.item_code

	return conditions, params


# ---------------------------------------------------------------------------
# KPI summary
# ---------------------------------------------------------------------------


def _get_report_summary(data):
	total_planned = sum(flt(r.get("planned_qty")) for r in data)
	total_actual = sum(flt(r.get("actual_qty")) for r in data)
	total_wastage = total_actual - total_planned

	return [
		{
			"value": len(data),
			"indicator": "blue",
			"label": _("Material Lines"),
			"datatype": "Int",
		},
		{
			"value": total_planned,
			"indicator": "grey",
			"label": _("Total Planned Qty"),
			"datatype": "Float",
		},
		{
			"value": total_actual,
			"indicator": "blue",
			"label": _("Total Consumed Qty"),
			"datatype": "Float",
		},
		{
			"value": total_wastage,
			"indicator": "red" if total_wastage > 0 else "green",
			"label": _("Total Wastage"),
			"datatype": "Float",
		},
	]
