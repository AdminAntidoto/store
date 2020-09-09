from odoo import models, api, fields


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _get_move_count(self):
        """
        Find all stock moves assiciated with the order
        @author: Keyur Kanani
        :return:
        """
        stock_move_obj = self.env['stock.move']
        stock_moves = stock_move_obj.search([('picking_id', '=', False), ('sale_line_id', 'in', self.order_line.ids)])
        self.moves_count = len(stock_moves)

    global_channel_id = fields.Many2one('global.channel.ept', string='Global Channel')
    moves_count = fields.Integer(compute="_get_move_count", string="Stock Move", store=False,
                                 help="Stock Move Count for Orders without Picking.")
    def create_sales_order_vals_ept(self, vals):
        """
        required parameter :- partner_id,partner_invoice_id,partner_shipping_id,
        company_id,warehouse_id,picking_policy,date_order
        Pass Dictionary
        vals = {'company_id':company_id,'partner_id':partner_id,
        'partner_invoice_id':partner_invoice_id,
        'partner_shipping_id':partner_shipping_id,'warehouse_id':warehouse_id,
        'company_id':company_id,
        'picking_policy':picking_policy,'date_order':date_order,'pricelist_id':pricelist_id,
        'payment_term_id':payment_term_id,'fiscal_position_id':fiscal_position_id,
        'invoice_policy':invoice_policy,'team_id':team_id,'client_order_ref':client_order_ref,
        'carrier_id':carrier_id,'invoice_shipping_on_delivery':invoice_shipping_on_delivery}
        """
        sale_order = self.env['sale.order']
        fpos = vals.get('fiscal_position_id', False)
        order_vals = {
            'company_id': vals.get('company_id'),
            'partner_id': vals.get('partner_id'),
            'partner_invoice_id': vals.get('partner_invoice_id'),
            'partner_shipping_id': vals.get('partner_shipping_id'),
            'warehouse_id': vals.get('warehouse_id'),
        }
        new_record = sale_order.new(order_vals)
        new_record.onchange_partner_id()  # Return Pricelist- Payment terms- Invoice address- Delivery address
        order_vals = sale_order._convert_to_write(
            {name: new_record[name] for name in new_record._cache})
        new_record = sale_order.new(order_vals)
        new_record.onchange_partner_shipping_id()  # Return Fiscal Position
        order_vals = sale_order._convert_to_write(
            {name: new_record[name] for name in new_record._cache})
        fpos = order_vals.get('fiscal_position_id', fpos)
        order_vals.update({
            'company_id': vals.get('company_id'),
            'picking_policy': vals.get('picking_policy'),
            'partner_invoice_id': vals.get('partner_invoice_id'),
            'partner_id': vals.get('partner_id'),
            'partner_shipping_id': vals.get('partner_shipping_id'),
            'date_order': vals.get('date_order', ''),
            'state': 'draft',
            'pricelist_id': vals.get('pricelist_id', ''),
            'fiscal_position_id': fpos,
            'payment_term_id': vals.get('payment_term_id', ''),
            'team_id': vals.get('team_id', ''),
            'client_order_ref': vals.get('client_order_ref', ''),
            'carrier_id': vals.get('carrier_id', '')
        })
        return order_vals

    @api.onchange('partner_shipping_id', 'partner_id')
    def onchange_partner_shipping_id(self):
        res = super(SaleOrder, self).onchange_partner_shipping_id()
        fiscal_position = False
        if self.warehouse_id:
            warehouse = self.warehouse_id
            origin_country_id = warehouse.partner_id and \
                                warehouse.partner_id.country_id and \
                                warehouse.partner_id.country_id.id or False
            origin_country_id = origin_country_id \
                                or (warehouse.company_id.partner_id.country_id
                                    and warehouse.company_id.partner_id.country_id.id or False)
            is_amz_customer = getattr(self.partner_id,'is_amz_customer', False)
            fiscal_position = self.env['account.fiscal.position'].with_context(
                    {'origin_country_ept': origin_country_id,'is_amazon_fpos':is_amz_customer,'force_company':warehouse.company_id.id}). \
                get_fiscal_position(self.partner_id.id, self.partner_shipping_id.id)
            self.fiscal_position_id = fiscal_position
        return res

    @api.onchange('warehouse_id')
    def onchange_warehouse_id(self):
        warehouse = self.warehouse_id
        if warehouse and self.partner_id:
            origin_country_id = warehouse.partner_id and warehouse.partner_id.country_id and \
                                warehouse.partner_id.country_id.id or False
            origin_country_id = origin_country_id \
                                or (warehouse.company_id.partner_id.country_id
                                    and warehouse.company_id.partner_id.country_id.id or False)
            is_amz_customer = getattr(self.partner_id,'is_amz_customer', False)
            fiscal_position_id = self.env['account.fiscal.position'].with_context(
                {'origin_country_ept': origin_country_id,'is_amazon_fpos':is_amz_customer,'force_company':warehouse.company_id.id}). \
                get_fiscal_position(self.partner_id.id, self.partner_shipping_id.id)
            self.fiscal_position_id = fiscal_position_id

    def _prepare_invoice(self):
        """This function is used to set global channel in account.move when create regular invoice
            @author: Dimpal added on 7/oct/2019
        """
        res = super(SaleOrder, self)._prepare_invoice()
        if self.global_channel_id:
            res.update({'global_channel_id': self.global_channel_id.id})
        return res

    def action_view_stock_move(self):
        """
        List All Stock Moves which is Associated for the Order
        @author: Keyur Kanani
        :return:
        """
        stock_move_obj = self.env['stock.move']
        records = stock_move_obj.search([('picking_id', '=', False), ('sale_line_id', 'in', self.order_line.ids)])
        action = {
            'domain': "[('id', 'in', " + str(records.ids) + " )]",
            'name': 'Order Stock Move',
            'view_mode': 'tree,form',
            'res_model': 'stock.move',
            'type': 'ir.actions.act_window',
        }
        return action
