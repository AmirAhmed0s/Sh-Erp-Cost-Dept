# Copyright (c) 2024, Amir Mansi and contributors
# For license information, please see license.txt

"""
Task Intelligence Dashboard
============================
Enterprise-grade Script Report for Tasks.

Features:
  • Colored priority & status badges
  • Auto-calculated Duration (Expected End - Expected Start)
  • Assigned-To Users collected from ToDo records
  • Overdue indicator
  • Aging (days open)
  • KPI summary cards (Open / Working / Overdue / Completed)
  • Optimised SQL with a single aggregate query
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = _get_columns()
	data = _get_data(filters)
	report_summary = _get_report_summary(data)
	return columns, data, None, None, report_summary


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------


def _get_columns():
	return [
		{
			"fieldname": "task_name",
			"label": _("Task ID"),
			"fieldtype": "Link",
			"options": "Task",
			"width": 130,
		},
		{
			"fieldname": "task_title",
			"label": _("Task Title"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "priority",
			"label": _("Priority"),
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"fieldname": "exp_start_date",
			"label": _("Expected Start"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "exp_end_date",
			"label": _("Expected End"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "duration",
			"label": _("Duration (Days)"),
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "assigned_to_users",
			"label": _("Assigned To"),
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"fieldname": "completed_on",
			"label": _("Completed On"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "completed_by",
			"label": _("Completed By"),
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"fieldname": "age_days",
			"label": _("Aging (Days)"),
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"fieldname": "task_creator",
			"label": _("Created By"),
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"fieldname": "is_overdue",
			"label": _("Overdue"),
			"fieldtype": "Data",
			"width": 80,
		},
	]


# ---------------------------------------------------------------------------
# Data query
# ---------------------------------------------------------------------------


def _get_data(filters):
	conditions, params = _build_conditions(filters)
	today = nowdate()

	# A single SQL query that fetches task data and aggregates assigned users
	# from the ToDo table in one pass (LEFT JOIN + GROUP_CONCAT).
	sql = f"""
		SELECT
			t.name                    AS task_name,
			t.subject                 AS task_title,
			t.priority,
			t.exp_start_date,
			t.exp_end_date,
			CASE
				WHEN t.exp_end_date IS NOT NULL AND t.exp_start_date IS NOT NULL
				THEN DATEDIFF(t.exp_end_date, t.exp_start_date)
				ELSE NULL
			END                       AS duration,
			t.status,
			COALESCE(t.custom_assigned_to_users,
				GROUP_CONCAT(DISTINCT td.allocated_to
					ORDER BY td.allocated_to SEPARATOR ', ')
			)                         AS assigned_to_users,
			t.completed_on,
			t.completed_by            AS completed_by,
			DATEDIFF(%(today)s, DATE(t.creation))  AS age_days,
			t.owner                   AS task_creator,
			CASE
				WHEN t.exp_end_date < %(today)s
				  AND t.status NOT IN ('Completed', 'Cancelled', 'Template')
				THEN 1 ELSE 0
			END                       AS is_overdue
		FROM
			`tabTask` t
			LEFT JOIN `tabToDo` td
				ON  td.reference_type = 'Task'
				AND td.reference_name = t.name
				AND td.status = 'Open'
		WHERE
			t.docstatus < 2
			{conditions}
		GROUP BY
			t.name
		ORDER BY
			FIELD(t.priority, 'Urgent', 'High', 'Medium', 'Low'),
			t.exp_end_date ASC
	"""

	params["today"] = today
	rows = frappe.db.sql(sql, params, as_dict=True)
	return rows


def _build_conditions(filters):
	conditions = ""
	params = {}

	if filters.get("from_date"):
		conditions += " AND t.creation >= %(from_date)s"
		params["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions += " AND t.creation <= %(to_date)s"
		params["to_date"] = filters.to_date

	if filters.get("status"):
		conditions += " AND t.status = %(status)s"
		params["status"] = filters.status

	if filters.get("priority"):
		conditions += " AND t.priority = %(priority)s"
		params["priority"] = filters.priority

	if filters.get("assigned_to"):
		conditions += (
			" AND EXISTS ("
			" SELECT 1 FROM `tabToDo` td2"
			" WHERE td2.reference_type = 'Task'"
			" AND td2.reference_name = t.name"
			" AND td2.allocated_to = %(assigned_to)s"
			" AND td2.status = 'Open'"
			")"
		)
		params["assigned_to"] = filters.assigned_to

	if filters.get("project"):
		conditions += " AND t.project = %(project)s"
		params["project"] = filters.project

	return conditions, params


# ---------------------------------------------------------------------------
# KPI summary (displayed as coloured cards above the report)
# ---------------------------------------------------------------------------


def _get_report_summary(data):
	"""
	Returns a list of KPI dicts for Frappe's built-in report_summary card row.
	Each card shows a count for a specific task status.
	"""
	totals = {
		"open": 0,
		"working": 0,
		"overdue": 0,
		"completed": 0,
	}

	for row in data:
		status = (row.get("status") or "").lower()
		is_overdue = row.get("is_overdue", 0)

		if is_overdue:
			totals["overdue"] += 1
		elif status == "open":
			totals["open"] += 1
		elif status == "working":
			totals["working"] += 1
		elif status == "completed":
			totals["completed"] += 1

	return [
		{
			"value": totals["open"],
			"indicator": "grey",
			"label": _("Open Tasks"),
			"datatype": "Int",
		},
		{
			"value": totals["working"],
			"indicator": "blue",
			"label": _("Working Tasks"),
			"datatype": "Int",
		},
		{
			"value": totals["overdue"],
			"indicator": "red",
			"label": _("Overdue Tasks"),
			"datatype": "Int",
		},
		{
			"value": totals["completed"],
			"indicator": "green",
			"label": _("Completed Tasks"),
			"datatype": "Int",
		},
	]
