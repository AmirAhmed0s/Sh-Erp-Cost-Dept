# Copyright (c) 2024, Amir Mansi and contributors
# For license information, please see license.txt

"""
Manufacturing Cost Analysis
============================
Shows the financial performance of production runs:
  • Planned cost  – derived from BOM (total_cost / quantity × wo_qty)
  • Actual cost   – recorded on the Work Order
  • Cost variance – actual minus planned
  • Variance %    – relative deviation from planned

KPI summary cards: Total Work Orders, Total Planned Cost,
                   Total Actual Cost, Total Variance.
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
			"fieldname": "name",
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
			"width": 160,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "bom_no",
			"label": _("BOM"),
			"fieldtype": "Link",
			"options": "BOM",
			"width": 140,
		},
		{
			"fieldname": "qty",
			"label": _("Planned Qty"),
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"fieldname": "produced_qty",
			"label": _("Produced Qty"),
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"fieldname": "planned_cost",
			"label": _("Planned Cost"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"fieldname": "actual_cost",
			"label": _("Actual Cost"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"fieldname": "cost_variance",
			"label": _("Cost Variance"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"fieldname": "variance_pct",
			"label": _("Variance %"),
			"fieldtype": "Percent",
			"width": 110,
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "planned_start_date",
			"label": _("Planned Start"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "planned_end_date",
			"label": _("Planned End"),
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
			wo.name,
			wo.production_item,
			i.item_name,
			wo.bom_no,
			wo.qty,
			wo.produced_qty,
			wo.status,
			wo.planned_start_date,
			wo.planned_end_date,
			-- Planned cost: BOM unit cost × WO quantity
			COALESCE(
				(b.total_cost / NULLIF(b.quantity, 0)) * wo.qty,
				0
			)                                    AS planned_cost,
			-- Actual cost stored on Work Order
			COALESCE(wo.actual_operating_cost, 0) AS actual_cost
		FROM
			`tabWork Order` wo
			LEFT JOIN `tabItem`  i ON i.name = wo.production_item
			LEFT JOIN `tabBOM`   b ON b.name  = wo.bom_no
		WHERE
			wo.docstatus = 1
			{conditions}
		ORDER BY
			wo.planned_start_date DESC,
			wo.name
	"""

	rows = frappe.db.sql(sql, params, as_dict=True)

	for row in rows:
		planned = flt(row.get("planned_cost"))
		actual = flt(row.get("actual_cost"))
		row["cost_variance"] = actual - planned
		row["variance_pct"] = (
			((actual - planned) / planned * 100) if planned else 0.0
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

	if filters.get("production_item"):
		conditions += " AND wo.production_item = %(production_item)s"
		params["production_item"] = filters.production_item

	if filters.get("status"):
		conditions += " AND wo.status = %(status)s"
		params["status"] = filters.status

	return conditions, params


# ---------------------------------------------------------------------------
# KPI summary cards
# ---------------------------------------------------------------------------


def _get_report_summary(data):
	total_planned = sum(flt(r.get("planned_cost")) for r in data)
	total_actual = sum(flt(r.get("actual_cost")) for r in data)
	total_variance = total_actual - total_planned

	return [
		{
			"value": len(data),
			"indicator": "blue",
			"label": _("Work Orders"),
			"datatype": "Int",
		},
		{
			"value": total_planned,
			"indicator": "grey",
			"label": _("Total Planned Cost"),
			"datatype": "Currency",
		},
		{
			"value": total_actual,
			"indicator": "blue",
			"label": _("Total Actual Cost"),
			"datatype": "Currency",
		},
		{
			"value": total_variance,
			"indicator": "red" if total_variance > 0 else "green",
			"label": _("Total Variance"),
			"datatype": "Currency",
		},
	]
