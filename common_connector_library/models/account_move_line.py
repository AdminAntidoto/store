from odoo import fields, models, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    global_channel_id = fields.Many2one('global.channel.ept', string='Global Channel')
    line_tax_amount_percent = fields.Float(digits='Line Tax Amount', string="Tax amount in per(%)")

    @api.onchange('amount_currency', 'currency_id', 'debit', 'credit', 'tax_ids', 'account_id',
                  'analytic_account_id', 'analytic_tag_ids', 'line_tax_amount_percent')
    def _onchange_mark_recompute_taxes(self):
        """
        Use: Super method Override and Add Line tax amount in onchange as Parameter
        set recompute_tax_line boolean as true which has not tax repartition line id for compute tax
        Params: {}
        Return: {}
        """
        ''' Recompute the dynamic onchange based on taxes.
        If the edited line is a tax line, don't recompute anything as the user must be able to
        set a custom value.
        '''
        return super(AccountMoveLine, self)._onchange_mark_recompute_taxes()

    @api.onchange('quantity', 'discount', 'price_unit', 'tax_ids', 'line_tax_amount_percent')
    def _onchange_price_subtotal(self):
        """
        Use: Super method Override and Pass Line tax amount in onchange as Parameter
        Params: {}
        Return: {}
        """
        return super(AccountMoveLine, self)._onchange_price_subtotal()

    @api.model
    def _get_price_total_and_subtotal_model(self, price_unit, quantity, discount, currency, product, partner, taxes,
                                            move_type):
        context = taxes._context
        if context:
            context = dict(context)
        else:
            context = {}
        context.update({'tax_computation_context': {'line_tax_amount_percent': self.line_tax_amount_percent}})
        taxes = taxes.with_context(context)
        return super(AccountMoveLine,
                     self.with_context({'tax_computation_context': {'line_tax_amount_percent': self.line_tax_amount_percent}})). \
            _get_price_total_and_subtotal_model(price_unit, quantity, discount, currency, product, partner, taxes,
                                                move_type)
