from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_done(self):
        """
        Added comment by Udit
        create and paid invoice on the basis of auto invoice work flow
        when invoicing policy is 'delivery'.
        """
        result = super(StockPicking, self).action_done()
        for picking in self:
            if picking.sale_id.invoice_status == 'invoiced':
                continue
            work_flow_process_record = picking.sale_id and picking.sale_id.auto_workflow_process_id
            if work_flow_process_record and picking.mapped('move_line_ids').filtered(
                    lambda l: l.product_id.invoice_policy == 'delivery') \
                    and work_flow_process_record.create_invoice \
                    and picking.picking_type_id.code == 'outgoing':
                if work_flow_process_record.create_invoice:
                    invoices = picking.sale_id._create_invoices()
                    picking.sale_id.validate_invoice_ept(invoices)
                    if work_flow_process_record.register_payment:
                        picking.sale_id.paid_invoice_ept(invoices)
        return result

    def get_set_product(self, product):
        """
        Added by Udit
        :param move: It will be sale order line object.
        :param product: Product object
        :return: This method will find bom of product and will return it's lines.
        """
        try:
            bom_obj = self.env['mrp.bom']
            bom_point = bom_obj.sudo()._bom_find(product=product)
            from_uom = product.uom_id
            to_uom = bom_point.product_uom_id
            factor = from_uom._compute_quantity(1, to_uom) / bom_point.product_qty
            bom, lines = bom_point.explode(product, factor, picking_type=bom_point.picking_type_id)
            return lines
        except:
            return {}
