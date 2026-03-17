// Copyright (c) 2024, Amir Mansi and contributors
// For license information, please see license.txt

/**
 * Assignment Control – Global UI Enforcement
 * -------------------------------------------
 * This script patches `frappe.desk.form.assign_to.add` so that the
 * assignment dialog only shows users that the current session user is
 * allowed to assign work to, based on their User Assignment Control record.
 *
 * The backend still validates every assignment independently (via the
 * ToDo validate hook), so this UI filter is a usability layer, not the
 * sole security mechanism.
 */

frappe.ready(function () {
	// Wait until the frappe desk modules are fully loaded
	frappe.after_ajax(function () {
		_patch_assign_to();
	});
});

function _patch_assign_to() {
	// Guard: module may not exist in all contexts (e.g., web pages)
	if (
		!frappe.desk ||
		!frappe.desk.form ||
		!frappe.desk.form.assign_to
	) {
		return;
	}

	const _original_add = frappe.desk.form.assign_to.add;

	frappe.desk.form.assign_to.add = function (opts) {
		// Fetch allowed assignees for the current user and this doctype
		frappe.call({
			method: "sh_erp_cost_dept.task_management.api.get_allowed_assignees",
			args: { doctype: opts.doctype },
			callback: function (r) {
				const allowed = r.message; // array of user IDs, or null

				if (!allowed) {
					// No restriction – open the standard dialog
					_original_add(opts);
					return;
				}

				// Wrap opts to inject an extra filter on the User field
				const patched_opts = Object.assign({}, opts);
				const _original_assign_callback = patched_opts.callback;

				// Override the method call by supplying a get_query on the
				// dialog's user field after it opens.
				const _original_after_render = patched_opts.after_render;
				patched_opts.after_render = function (dialog) {
					// Restrict the user field to allowed users only
					const user_field = dialog.get_field
						? dialog.get_field("assign_to")
						: null;

					if (user_field && user_field.set_query) {
						user_field.set_query(function () {
							return {
								filters: [["User", "name", "in", allowed]],
							};
						});
					}

					if (_original_after_render) {
						_original_after_render(dialog);
					}
				};

				_original_add(patched_opts);
			},
			error: function () {
				// On error fall back to the standard (unrestricted) dialog
				_original_add(opts);
			},
		});
	};
}
