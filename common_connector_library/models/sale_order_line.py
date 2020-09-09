from odoo import models, fields, api


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    line_tax_amount_percent = fields.Float(digits='Line Tax Amount', default=0.00, string="Tax Amount In Percentage(%)",
                                           help="Order line Tax")

    def create_sale_order_line_ept(self, vals):
        """
        pass Dictionary
        vals = {'order_id':order_id,'product_id':product_id,'company_id':company_id,
        'description':product_name,'order_qty':qty,'price_unit':price,'discount':discount}
        Required Parameter :- order_id,name,product_id
        """
        sale_order_line = self.env['sale.order.line']
        order_line = {
            'order_id': vals.get('order_id'),
            'product_id': vals.get('product_id', ''),
            'company_id': vals.get('company_id', ''),
            'name': vals.get('description'),
            'product_uom': vals.get('product_uom')
        }
        new_order_line = sale_order_line.new(order_line)
        new_order_line.product_id_change()
        order_line = sale_order_line._convert_to_write(
            {name: new_order_line[name] for name in new_order_line._cache})
        order_line.update({
            'order_id': vals.get('order_id'),
            'product_uom_qty': vals.get('order_qty', 0.0),
            'price_unit': vals.get('price_unit', 0.0),
            'discount': vals.get('discount', 0.0),
            'state': 'draft',
        })
        return order_line

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id', 'line_tax_amount_percent')
    def _compute_amount(self):
        """
        Use: Override method for Compute Line tax amount in sale order line
        Params: self => sale.order.line
        Return: {}
        """
        if sum(self.mapped('line_tax_amount_percent')) > 0:
            for line in self:
                line_tax = line.line_tax_amount_percent or 0.0
                super(SaleOrderLine, line.with_context(
                    {'tax_computation_context': {'line_tax_amount_percent': line_tax}}))._compute_amount()
        else:
            return super(SaleOrderLine, self)._compute_amount()

    def _prepare_invoice_line(self):
        """
        Use: Inherited method for set Line tax amount in Invoice line (Account Move Line)
        from sale order line
        Params: self => sale.order.line
        Return: res => {vals}
        """
        res = super(SaleOrderLine, self)._prepare_invoice_line()
        if self.invoice_lines:
            res.update({'line_tax_amount_percent': self.invoice_lines[0].line_tax_amount_percent})

        if self.line_tax_amount_percent:
            res.update({'line_tax_amount_percent': self.line_tax_amount_percent})
        # else:
        #     res.update({'line_tax_amount_percent': self.line_tax_amount})
        return res
