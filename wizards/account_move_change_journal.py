from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountMoveChangeJournal(models.TransientModel):
    _name = "account.move.change.journal"
    _description = "Change Journal of Account Move"

    @api.model
    def _get_moves(self):
        """Get the moves from context"""
        move_ids = self._context.get("active_ids", [])
        return self.env["account.move"].browse(move_ids)

    move_ids = fields.Many2many(
        "account.move",
        string="Moves",
        default=_get_moves,
        readonly=True,
    )
    journal_from_id = fields.Many2one(
        "account.journal",
        string="Current Journal",
        compute="_compute_journal_from",
        store=True,
    )
    journal_to_id = fields.Many2one(
        "account.journal",
        string="New Journal",
        required=True,
        help="Select the journal to which you want to move the transactions",
    )
    force_change = fields.Boolean(
        string="Force Change",
        default=False,
        help="Force the change even if there are warnings (use with caution)",
    )
    warning_message = fields.Html(
        string="Warnings",
        compute="_compute_warnings",
    )
    move_count = fields.Integer(
        string="Number of Moves",
        compute="_compute_move_count",
    )
    reset_sequence = fields.Boolean(
        string="Reset Sequence",
        default=True,
        help="If checked, the move will get a new sequence number from the target journal",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        compute="_compute_company_id",
        store=True,
    )

    @api.depends("move_ids")
    def _compute_move_count(self):
        for wizard in self:
            wizard.move_count = len(wizard.move_ids)

    @api.depends("move_ids")
    def _compute_company_id(self):
        for wizard in self:
            companies = wizard.move_ids.mapped("company_id")
            if len(companies) == 1:
                wizard.company_id = companies[0]
            else:
                wizard.company_id = self.env.company

    @api.depends("move_ids")
    def _compute_journal_from(self):
        for wizard in self:
            journals = wizard.move_ids.mapped("journal_id")
            if len(journals) == 1:
                wizard.journal_from_id = journals[0]
            else:
                wizard.journal_from_id = False

    @api.depends("move_ids", "journal_to_id", "force_change")
    def _compute_warnings(self):
        for wizard in self:
            warnings = []

            if not wizard.move_ids:
                warnings.append("<li>No moves selected</li>")

            if wizard.journal_to_id:
                # Check if moves are posted
                posted_moves = wizard.move_ids.filtered(lambda m: m.state == "posted")
                if posted_moves:
                    warnings.append(
                        f"<li><b>Warning:</b> {len(posted_moves)} move(s) are posted. "
                        "Changing the journal of posted moves may affect accounting integrity.</li>"
                    )

                # Check for different journals
                journals = wizard.move_ids.mapped("journal_id")
                if len(journals) > 1:
                    warnings.append(
                        f"<li><b>Info:</b> Selected moves come from {len(journals)} different journals.</li>"
                    )

                # Check for reconciled moves
                reconciled_moves = wizard.move_ids.filtered(
                    lambda m: any(line.reconciled for line in m.line_ids)
                )
                if reconciled_moves:
                    warnings.append(
                        f"<li><b>Warning:</b> {len(reconciled_moves)} move(s) have reconciled lines. "
                        "This operation will not unreconcile them.</li>"
                    )

                # Check for different move types
                move_types = wizard.move_ids.mapped("move_type")
                if len(move_types) > 1:
                    warnings.append(
                        f"<li><b>Info:</b> Selected moves have different types: "
                        f"{', '.join(set(move_types))}.</li>"
                    )

                # Check if target journal supports move types
                for move in wizard.move_ids:
                    if move.move_type and wizard.journal_to_id.type != move.journal_id.type:
                        warnings.append(
                            f"<li><b>Warning:</b> Move {move.name} has type '{move.move_type}' "
                            f"but target journal type is '{wizard.journal_to_id.type}'. "
                            "This may cause issues.</li>"
                        )
                        break

            if warnings:
                wizard.warning_message = "<ul>" + "".join(warnings) + "</ul>"
            else:
                wizard.warning_message = False

    def _validate_change(self):
        """Validate that the change can be performed"""
        self.ensure_one()

        if not self.move_ids:
            raise UserError(_("No moves selected to change journal."))

        if not self.journal_to_id:
            raise UserError(_("Please select a target journal."))

        # Check if any move is the same journal
        same_journal_moves = self.move_ids.filtered(
            lambda m: m.journal_id == self.journal_to_id
        )
        if same_journal_moves and len(same_journal_moves) == len(self.move_ids):
            raise UserError(
                _("All selected moves already belong to the target journal '%s'.")
                % self.journal_to_id.name
            )

        # Validate that moves can be modified
        for move in self.move_ids:
            if move.state == "posted" and not self.force_change:
                if move.restrict_mode_hash_table:
                    raise UserError(
                        _("Cannot change journal of move '%s' because it is posted "
                          "and locked by hash. Please use 'Force Change' if you really "
                          "need to proceed (not recommended).") % move.name
                    )

    def _prepare_move_values(self, move):
        """Prepare the values to update the move"""
        values = {
            "journal_id": self.journal_to_id.id,
        }

        # Reset sequence if requested
        if self.reset_sequence:
            values["name"] = "/"

        return values

    def action_change_journal(self):
        """Execute the journal change"""
        self.ensure_one()
        self._validate_change()

        moves_to_change = self.move_ids.filtered(
            lambda m: m.journal_id != self.journal_to_id
        )

        if not moves_to_change:
            raise UserError(_("No moves to change. All moves already belong to the target journal."))

        # Process each move
        changed_moves = self.env["account.move"]
        errors = []

        for move in moves_to_change:
            try:
                old_journal = move.journal_id.name
                old_name = move.name

                # Prepare values
                values = self._prepare_move_values(move)

                # Write changes with proper context
                move.with_context(
                    check_move_validity=False,
                    skip_invoice_sync=True,
                ).write(values)

                # If name was reset and move is posted, trigger renumbering
                if self.reset_sequence and values.get("name") == "/" and move.state == "posted":
                    # Odoo will automatically assign a new number on write
                    move._compute_name()

                # Post message in chatter for audit trail
                message = _(
                    "Journal changed from <b>%s</b> to <b>%s</b>"
                ) % (old_journal, self.journal_to_id.name)

                if old_name != move.name:
                    message += _("<br/>Sequence changed from <b>%s</b> to <b>%s</b>") % (
                        old_name,
                        move.name,
                    )

                move.message_post(body=message)
                changed_moves |= move

            except Exception as e:
                errors.append(f"Move {move.name}: {str(e)}")

        # Show results
        if errors:
            error_msg = _("Some moves could not be changed:\n") + "\n".join(errors)
            if changed_moves:
                error_msg = _(
                    "%s moves successfully changed.\n\n%s"
                ) % (len(changed_moves), error_msg)
            raise UserError(error_msg)

        # Success message
        message = _("%s move(s) successfully changed to journal '%s'.") % (
            len(changed_moves),
            self.journal_to_id.name,
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
