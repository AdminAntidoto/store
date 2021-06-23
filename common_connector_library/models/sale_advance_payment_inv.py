from odoo import models


class SaleAadvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def _create_invoice(self, order, so_line, amount):
        """This function is used for set global channel when create down payment invoices...
            @author: Dimpal added on 7/oct/2019
        """
        res = super(SaleAadvancePaymentInv, self)._create_invoice(order, so_line, amount)
        if order.global_channel_id:
            res.global_channel_id = order.global_channel_id.id
            for aml in res.line_ids:
                aml.global_channel_id = order.global_channel_id.id
        return res
