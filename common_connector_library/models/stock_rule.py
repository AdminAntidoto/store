from odoo import models

"""This class is inherit for set global channel id in stock.move from sale order
@author: Dimpal
@added on: 5/oct/2019
"""


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, product_id, product_qty, product_uom, location_id, name,
                               origin, company_id, values):
        """This function is used to set global channel id in stock.move from sale order
            @author: Dimpal added on 5/oct/2019
        """
        res = super(StockRule, self)._get_stock_move_values(product_id, product_qty, product_uom,
                                                            location_id, name, origin, company_id,
                                                            values)
        if res.get('sale_line_id'):
            sale_line_obj = self.env['sale.order.line'].browse(res.get('sale_line_id'))
            global_channel_id = sale_line_obj.order_id.global_channel_id.id
            res.update({'global_channel_id': global_channel_id})
        return res
