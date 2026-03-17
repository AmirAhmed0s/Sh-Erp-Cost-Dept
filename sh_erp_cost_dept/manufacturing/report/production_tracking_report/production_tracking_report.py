# Copyright (c) 2024, Amir Mansi and contributors
# For license information, please see license.txt

"""
Production Tracking Report
===========================
Tracks Work Order execution and highlights delays:
  • Planned vs actual start / end dates
  • Completion rate (produced qty / planned qty)
  • Delay days (actual end vs planned end, or days open past deadline)
  • Status badges

KPI summary cards: Total WOs, Completed, In Process, Delayed.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


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
			"fieldname": "completion_rate",
			"label": _("Completion %"),
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
		{
			"fieldname": "actual_start_date",
			"label": _("Actual Start"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "actual_end_date",
			"label": _("Actual End"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "delay_days",
			"label": _("Delay (Days)"),
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"fieldname": "is_delayed",
			"label": _("Delayed"),
			"fieldtype": "Data",
			"width": 80,
		},
	]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def _get_data(filters):
	conditions, params = _build_conditions(filters)
	today = nowdate()
	params["today"] = today

	sql = f"""
		SELECT
			wo.name,
			wo.production_item,
			i.item_name,
			wo.qty,
			wo.produced_qty,
			wo.status,
			wo.planned_start_date,
			wo.planned_end_date,
			wo.actual_start_date,
			wo.actual_end_date,
			-- Delay: days between planned end and actual end (or today for open orders)
			CASE
				WHEN wo.actual_end_date IS NOT NULL
					THEN DATEDIFF(wo.actual_end_date, wo.planned_end_date)
				WHEN wo.planned_end_date < %(today)s
				  AND wo.status NOT IN ('Completed', 'Stopped')
					THEN DATEDIFF(%(today)s, wo.planned_end_date)
				ELSE 0
			END AS delay_days,
			CASE
				WHEN wo.planned_end_date < %(today)s
				  AND wo.status NOT IN ('Completed', 'Stopped')
					THEN 1
				WHEN wo.actual_end_date > wo.planned_end_date
					THEN 1
				ELSE 0
			END AS is_delayed
		FROM
			`tabWork Order` wo
			LEFT JOIN `tabItem` i ON i.name = wo.production_item
		WHERE
			wo.docstatus = 1
			{conditions}
		ORDER BY
			wo.planned_end_date ASC,
			wo.name
	"""

	rows = frappe.db.sql(sql, params, as_dict=True)

	for row in rows:
		planned = flt(row.get("qty"))
		produced = flt(row.get("produced_qty"))
		row["completion_rate"] = (produced / planned * 100) if planned else 0.0
		row["is_delayed"] = "⚠ Yes" if row.get("is_delayed") else "✓ No"

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
# KPI summary
# ---------------------------------------------------------------------------


def _get_report_summary(data):
	totals = {"total": len(data), "completed": 0, "in_process": 0, "delayed": 0}

	for row in data:
		status = (row.get("status") or "").lower()
		if status == "completed":
			totals["completed"] += 1
		elif status == "in process":
			totals["in_process"] += 1
		if row.get("is_delayed", "").startswith("⚠"):
			totals["delayed"] += 1

	return [
		{
			"value": totals["total"],
			"indicator": "blue",
			"label": _("Total Work Orders"),
			"datatype": "Int",
		},
		{
			"value": totals["completed"],
			"indicator": "green",
			"label": _("Completed"),
			"datatype": "Int",
		},
		{
			"value": totals["in_process"],
			"indicator": "blue",
			"label": _("In Process"),
			"datatype": "Int",
		},
		{
			"value": totals["delayed"],
			"indicator": "red",
			"label": _("Delayed"),
			"datatype": "Int",
		},
	]
