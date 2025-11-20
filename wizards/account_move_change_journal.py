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

    def _get_related_payments(self):
        """Get payments related to the selected moves"""
        self.ensure_one()
        payments = self.env["account.payment"].search([
            ("move_id", "in", self.move_ids.ids)
        ])
        return payments

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

                # Check for related payments
                related_payments = wizard._get_related_payments()
                if related_payments:
                    warnings.append(
                        f"<li><b>Info:</b> {len(related_payments)} payment(s) will also have their journal changed.</li>"
                    )

                    # Check if target journal has proper payment method configuration
                    for payment in related_payments:
                        available_methods = wizard.journal_to_id._get_available_payment_method_lines(
                            payment.payment_type
                        )
                        if not available_methods:
                            warnings.append(
                                f"<li><b>Error:</b> Journal '{wizard.journal_to_id.name}' has no payment methods "
                                f"configured for {payment.payment_type} payments. "
                                f"Payment {payment.name} cannot be changed.</li>"
                            )
                            break

                        # Check if any method has outstanding account
                        methods_with_account = available_methods.filtered(lambda l: l.payment_account_id)
                        if not methods_with_account:
                            # Check company defaults
                            company = wizard.journal_to_id.company_id
                            if payment.payment_type == 'inbound':
                                has_default = bool(company.account_journal_payment_debit_account_id)
                            else:
                                has_default = bool(company.account_journal_payment_credit_account_id)

                            if not has_default:
                                warnings.append(
                                    f"<li><b>Error:</b> Journal '{wizard.journal_to_id.name}' payment methods "
                                    f"have no outstanding account configured, and company has no defaults. "
                                    f"Please configure the outstanding payments/receipts account.</li>"
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

    def _change_payment_journal(self, payment):
        """Change the journal of a related payment"""
        try:
            old_journal = payment.journal_id.name

            # Get a compatible payment method line for the new journal
            available_method_lines = self.journal_to_id._get_available_payment_method_lines(
                payment.payment_type
            )

            # Try to find a payment method with the same code that has an outstanding account
            new_payment_method_line = False
            if payment.payment_method_line_id:
                current_code = payment.payment_method_line_id.code
                # First try to find one with the same code AND with payment_account_id
                matching_method = available_method_lines.filtered(
                    lambda l: l.code == current_code and l.payment_account_id
                )
                if matching_method:
                    new_payment_method_line = matching_method[0]
                else:
                    # If not found with account, try just with same code
                    matching_method = available_method_lines.filtered(
                        lambda l: l.code == current_code
                    )
                    if matching_method:
                        new_payment_method_line = matching_method[0]

            # If still not found, try to get any method with payment_account_id
            if not new_payment_method_line:
                methods_with_account = available_method_lines.filtered(
                    lambda l: l.payment_account_id
                )
                if methods_with_account:
                    new_payment_method_line = methods_with_account[0]
                elif available_method_lines:
                    new_payment_method_line = available_method_lines[0]

            # Validate that we have a valid payment method
            if not new_payment_method_line:
                return False, _(
                    "The target journal '%s' has no payment methods configured for %s payments."
                ) % (self.journal_to_id.name, payment.payment_type)

            # Check if the payment method has an outstanding account
            # If not, check if the journal has a default account we can use
            if not new_payment_method_line.payment_account_id:
                # Check company's default outstanding accounts
                company = self.journal_to_id.company_id
                if payment.payment_type == 'inbound':
                    default_account = company.account_journal_payment_debit_account_id
                else:
                    default_account = company.account_journal_payment_credit_account_id

                if not default_account:
                    return False, _(
                        "The payment method '%s' in journal '%s' has no outstanding account configured, "
                        "and the company has no default outstanding account. "
                        "Please configure the outstanding payments/receipts account in the journal or company settings."
                    ) % (new_payment_method_line.name, self.journal_to_id.name)

            # Get the appropriate receiptbook for the new journal's company
            new_receiptbook_id = False
            if not payment.is_internal_transfer:
                # Check if the company uses receiptbooks
                new_company = self.journal_to_id.company_id
                if hasattr(new_company, 'use_receiptbook') and new_company.use_receiptbook:
                    new_receiptbook = self.env["account.payment.receiptbook"].search([
                        ("partner_type", "=", payment.partner_type),
                        ("company_id", "=", new_company.id),
                    ], limit=1)
                    if new_receiptbook:
                        new_receiptbook_id = new_receiptbook.id

            # Update payment using direct SQL to avoid _synchronize_to_moves
            # which tries to update readonly fields on posted moves
            self.env.cr.execute("""
                UPDATE account_payment
                SET journal_id = %s,
                    payment_method_line_id = %s,
                    receiptbook_id = %s,
                    is_reconciled = %s,
                    write_date = NOW(),
                    write_uid = %s
                WHERE id = %s
            """, (
                self.journal_to_id.id,
                new_payment_method_line.id,
                new_receiptbook_id if new_receiptbook_id else None,
                False,
                self.env.uid,
                payment.id,
            ))

            # Invalidate cache to ensure Odoo sees the new values
            payment.invalidate_recordset(['journal_id', 'payment_method_line_id', 'receiptbook_id', 'is_reconciled'])

            # Recompute dependent fields
            payment.invalidate_recordset([
                'currency_id',
                'available_payment_method_line_ids',
                'outstanding_account_id',
                'company_id',
            ])

            # Post message in chatter for audit trail
            message = _(
                "Journal changed from <b>%s</b> to <b>%s</b> (updated automatically with related move)"
            ) % (old_journal, self.journal_to_id.name)

            payment.message_post(body=message)
            return True, None
        except Exception as e:
            return False, str(e)

    def action_change_journal(self):
        """Execute the journal change"""
        self.ensure_one()
        self._validate_change()

        moves_to_change = self.move_ids.filtered(
            lambda m: m.journal_id != self.journal_to_id
        )

        if not moves_to_change:
            raise UserError(_("No moves to change. All moves already belong to the target journal."))

        # Get related payments before changing moves
        related_payments = self._get_related_payments()

        # Process each move
        changed_moves = self.env["account.move"]
        changed_payments = self.env["account.payment"]
        errors = []

        # IMPORTANT: First process payments, then moves
        # This is because the payment's _synchronize_to_moves method would overwrite
        # the move's journal_id if we did it the other way around.
        # By changing payments first with skip_account_move_synchronization=True,
        # then changing moves, we ensure both stay in sync.

        # Process related payments FIRST
        for payment in related_payments:
            if payment.journal_id != self.journal_to_id:
                success, error = self._change_payment_journal(payment)
                if success:
                    changed_payments |= payment
                else:
                    errors.append(f"Payment {payment.name}: {error}")

        # Then process moves
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
                    skip_account_move_synchronization=True,
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
            error_msg = _("Some moves/payments could not be changed:\n") + "\n".join(errors)
            if changed_moves or changed_payments:
                success_msg = ""
                if changed_moves:
                    success_msg += _("%s move(s) successfully changed. ") % len(changed_moves)
                if changed_payments:
                    success_msg += _("%s payment(s) successfully changed.") % len(changed_payments)
                error_msg = success_msg + "\n\n" + error_msg
            raise UserError(error_msg)

        # Success message
        message = _("%s move(s) successfully changed to journal '%s'.") % (
            len(changed_moves),
            self.journal_to_id.name,
        )

        if changed_payments:
            message += _("\n%s related payment(s) also changed.") % len(changed_payments)

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
