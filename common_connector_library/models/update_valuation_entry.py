from odoo import fields, models

"""This class is used for update valuation entries
    In this update amount currency field of account.move.line
    based on order currency and received date rate
    @author: Dimpal
    @added on: 4/Oct/2019
"""


class StockMove(models.Model):
    _inherit = 'stock.move'

    # Added By Dimpal on 5/oct/2019
    global_channel_id = fields.Many2one('global.channel.ept', string='Global Channel')

    """
    def _generate_valuation_lines_data(self, partner_id, qty, debit_value, credit_value,
                                       debit_account_id, credit_account_id, description):
        res = super(StockMove, self)._generate_valuation_lines_data(partner_id, qty, debit_value,
                                                                    credit_value, debit_account_id,
                                                                    credit_account_id, description)

        if self.sale_line_id.currency_id.id != self.company_id.currency_id.id:
            company_id = self.company_id
            date = self.env['stock.valuation.layer'].search([
                ('product_id', '=', self.product_id.id),
                ('remaining_qty', '>', 0),
                ('company_id', '=', company_id.id)
            ], order='id', limit=1).create_date

            currency_id = company_id.currency_id.with_context(date=date)
            order_currency = self.sale_line_id.currency_id
            if debit_value == credit_value:
                amt_currency = currency_id.compute(debit_value, order_currency)
                res.get('debit_line_vals').update(
                    {'amount_currency': amt_currency, 'currency_id': order_currency.id})
                res.get('credit_line_vals').update(
                    {'amount_currency': amt_currency * -1, 'currency_id': order_currency.id})
            else:
                debit_amt_currency = currency_id.compute(debit_value, order_currency)
                credit_amt_currency = currency_id.compute(credit_value, order_currency)
                res.get('debit_line_vals').update(
                    {'amount_currency': debit_amt_currency, 'currency_id': order_currency.id})
                res.get('credit_line_vals').update(
                    {'amount_currency': credit_amt_currency * -1, 'currency_id': order_currency.id})

        # set global channel id when creating valuation journal entries...
        if self.global_channel_id:
            res.get('debit_line_vals').update({'global_channel_id': self.global_channel_id.id})
            res.get('credit_line_vals').update({'global_channel_id': self.global_channel_id.id})

        return res
"""

    def _search_picking_for_assignation(self):
        """This function is used to set global channel in stock.picking when assign_picking
            @author: Dimpal added on 7/oct/2019
        """
        res = super(StockMove, self)._search_picking_for_assignation()
        if res and self.global_channel_id:
            res.global_channel_id = self.global_channel_id.id
        return res

    def _get_new_picking_values(self):
        """This function is used to set global channel in stock.picking when assign_picking
            @author: Dimpal added on 7/oct/2019
        """
        res = super(StockMove, self)._get_new_picking_values()
        if self.global_channel_id:
            res['global_channel_id'] = self.global_channel_id.id
        return res
