# Copyright (c) 2024, Amir Mansi and contributors
# For license information, please see license.txt

"""
Task Management - Assignment Control API
==========================================
Whitelisted endpoints and document-event hooks for enforcing assignment
restrictions defined in User Assignment Control records.

Architecture:
  • get_allowed_assignees()   - called by the UI to filter the user list
  • validate_assignment()     - called by UI before submitting an assignment
  • validate_todo_assignment() - document-event hook on ToDo (before_insert)
  • update_task_assigned_users() - document-event hook on ToDo (after_insert /
                                   on_update / on_trash / after_cancel)
"""

import frappe
from frappe import _

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_control_for_user(user):
	"""
	Returns the User Assignment Control record (name + apply_scope) for a
	given user if one exists and is active; otherwise returns None.
	"""
	return frappe.db.get_value(
		"User Assignment Control",
		{"manager": user, "is_active": 1},
		["name", "apply_scope"],
		as_dict=True,
	)


def _doctype_in_scope(control_name, doctype):
	"""Returns True if *doctype* is listed in the control's allowed_doctypes."""
	return bool(
		frappe.db.exists(
			"Assignment Allowed DocType",
			{"parent": control_name, "doctype_name": doctype},
		)
	)


def _get_allowed_users_for_control(control_name):
	"""Returns the list of user IDs in the control's allowed_users child table."""
	rows = frappe.get_all(
		"Assignment Allowed User",
		filters={"parent": control_name},
		fields=["user"],
	)
	return [r.user for r in rows]


# ---------------------------------------------------------------------------
# Whitelisted API endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_allowed_assignees(doctype=None):
	"""
	Returns the list of user IDs the *current session user* is allowed to
	assign work to, or ``None`` when no restriction is configured.

	Called by the UI before opening the assignment dialog so the dialog
	can filter its user list accordingly.
	"""
	current_user = frappe.session.user
	control = _get_control_for_user(current_user)

	if not control:
		return None  # No restriction - all users are assignable

	# Check scope: if "Custom Selection", only apply for listed DocTypes
	if control.apply_scope == "Custom Selection" and doctype:
		if not _doctype_in_scope(control.name, doctype):
			return None  # Not in scope - no restriction for this DocType

	return _get_allowed_users_for_control(control.name)


@frappe.whitelist()
def validate_assignment(allocated_to, reference_type=None):
	"""
	Validates that the *current session user* is permitted to assign work
	to *allocated_to*.  Raises a ``frappe.ValidationError`` if the assignment
	is not allowed; returns ``True`` otherwise.

	Can be called from the UI as a pre-flight check before calling the
	standard ``frappe.desk.form.assign_to.add`` endpoint.
	"""
	allowed = get_allowed_assignees(doctype=reference_type)

	if allowed is None:
		return True  # No restriction

	if allocated_to not in allowed:
		frappe.throw(
			_("You are not permitted to assign work to {0}.  Please select from the allowed users.").format(
				frappe.bold(allocated_to)
			),
			title=_("Assignment Restricted"),
		)

	return True


# ---------------------------------------------------------------------------
# Document-event hooks
# ---------------------------------------------------------------------------


def validate_todo_assignment(doc, method=None):
	"""
	Hook: ``doc_events → ToDo → validate``

	Enforces assignment restrictions at the backend level so that no
	assignment can bypass the UI control (e.g., via direct API calls).
	"""
	# Allow Administrator and internal system calls to bypass the check
	if frappe.session.user in ("Administrator", "Guest"):
		return
	if frappe.flags.get("ignore_assignment_control"):
		return

	# Only validate newly-created open assignments or when the assignee changes
	if doc.status != "Open" or (not doc.is_new() and not doc.has_value_changed("allocated_to")):
		return

	owner = doc.owner or frappe.session.user
	control = _get_control_for_user(owner)

	if not control:
		return  # No restriction for this user

	# Scope check
	if control.apply_scope == "Custom Selection":
		if not _doctype_in_scope(control.name, doc.reference_type):
			return  # DocType not in scope

	allowed_users = _get_allowed_users_for_control(control.name)

	if doc.allocated_to not in allowed_users:
		frappe.throw(
			_("You are not permitted to assign {0} to user {1}.").format(
				frappe.bold(doc.reference_type or "this document"),
				frappe.bold(doc.allocated_to),
			),
			title=_("Assignment Restricted"),
		)


def update_task_assigned_users(doc, method=None):
	"""
	Hook: ``doc_events → ToDo → after_insert / on_update / on_trash``

	Keeps the Task.custom_assigned_to_users denormalized field up-to-date
	whenever an assignment changes so that the Task Intelligence Dashboard
	can display it without an extra join.
	"""
	if doc.reference_type != "Task" or not doc.reference_name:
		return

	if not frappe.db.exists("Task", doc.reference_name):
		return

	assignees = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Task",
			"reference_name": doc.reference_name,
			"status": "Open",
		},
		fields=["allocated_to"],
	)

	users_str = ", ".join(a.allocated_to for a in assignees if a.allocated_to)

	frappe.db.set_value(
		"Task",
		doc.reference_name,
		"custom_assigned_to_users",
		users_str,
		update_modified=False,
	)
