from odoo import models, fields, _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    auto_workflow_process_id = fields.Many2one('sale.workflow.process.ept',
                                               string='Workflow Process', copy=False)

    def _prepare_invoice(self):
        """
        Added comment by Udit
        This method let the invoice date will be the same as the order date.
        """
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.auto_workflow_process_id:
            #invoice_vals.update({'journal_id': self.auto_workflow_process_id.sale_journal_id.id})
            if self.auto_workflow_process_id.invoice_date_is_order_date:
                invoice_vals['date'] = self.date_order.date()
                invoice_vals['invoice_date'] = fields.Date.context_today(self)
        return invoice_vals

    def validate_order_ept(self):
        """ 
        This function validate sales order and write date order same as previous order
        Because Odoo change date order as current date in action confirm process.
        @author: Dipesh Tanna
        """
        self.ensure_one()
        date_order = self.date_order
        self.action_confirm()
        self.write({'date_order': date_order})
        return True

    def process_orders_and_invoices_ept(self):
        """
        This method will confirm sale orders, create and paid related invoices.
        :param work_flow_process_record: Work flow object
        """
        for order in self:
            work_flow_process_record = order.auto_workflow_process_id

            if order.invoice_status and order.invoice_status == 'invoiced':
                continue

            if work_flow_process_record.validate_order:
                order.validate_order_ept()

            if not order.mapped('order_line').filtered(
                    lambda l: l.product_id.invoice_policy == 'order'):
                continue

            order.validate_and_paid_invoices_ept(work_flow_process_record)
        return True

    def validate_and_paid_invoices_ept(self, work_flow_process_record):
        """
        This method will create invoices, validate it and paid it, according
        to the configuration in workflow sets in quotation.
        :param work_flow_process_record:
        :return: It will return boolean.
        """
        self.ensure_one()
        if work_flow_process_record.create_invoice:
            ctx = self._context.copy()
            ctx.update({'journal_ept': work_flow_process_record.sale_journal_id})
            invoices = self.with_context(ctx)._create_invoices()
            self.validate_invoice_ept(invoices)
            if work_flow_process_record.register_payment:
                self.paid_invoice_ept(invoices)
        return True

    def validate_invoice_ept(self, invoices):
        """
        Added by Udit
        This methid will validate and paid invoices.
        :param work_flow_process_record: Work flow object
        """
        self.ensure_one()
        for invoice in invoices:
            invoice.action_post()
        return True

    def paid_invoice_ept(self, invoices):
        """
        This method auto paid invoice based on auto workflow method.
        @author: Dipesh Tanna
        """
        self.ensure_one()
        account_payment_obj = self.env['account.payment']
        for invoice in invoices:
            if invoice.amount_residual:
                vals = invoice.prepare_payment_dict(self.auto_workflow_process_id)
                new_rec = account_payment_obj.create(vals)
                new_rec.post()
        return True

    def auto_shipped_order_ept(self, customers_location, is_mrp_installed=False):
        """
        Added by Udit
        :param customers_location: It is customer location object.
        :param is_mrp_installed: It is a boolean for mrp installed or not.
        :return: This method will generate stock move and done it, it will return boolean.
        """
        order_lines = self.order_line.filtered(lambda l: l.product_id.type != 'service')
        picking_obj = self.env['stock.picking']
        for order_line in order_lines:
            if not is_mrp_installed:
                self.create_and_done_stock_move(order_line, customers_location)
            else:
                bom_lines = picking_obj.get_set_product(order_line.product_id)
                for bom_line in bom_lines:
                    self.create_and_done_stock_move(order_line, customers_location, bom_line)
                if not bom_lines:
                    self.create_and_done_stock_move(order_line, customers_location)
        return True

    def create_and_done_stock_move(self, order_line, customers_location, bom_line=False):
        """
        Added by Udit
        :param order_line: It is sale order line.
        :param customers_location: It is customer location.
        :return: It will create and done stock move as per the data
                in order line and return boolean.
        """
        if bom_line:
            product = bom_line[0].product_id
            product_qty = bom_line[1].get('qty', 0) * order_line.product_uom_qty
            product_uom = bom_line[0].product_uom_id
        else:
            product = order_line.product_id
            product_qty = order_line.product_uom_qty
            product_uom = order_line.product_uom
        if product and product_qty and product_uom:
            vals = {
                'name': _('Auto processed move : %s') %
                        (product.description_sale if product.description_sale
                         else order_line.name),
                'company_id': self.company_id.id,
                'product_id': product.id if product else False,
                'product_uom_qty': product_qty,
                'product_uom': product_uom.id if product_uom else False,
                'location_id': self.warehouse_id.lot_stock_id.id,
                'location_dest_id': customers_location.id,
                'state': 'confirmed',
                'sale_line_id': order_line.id
            }
            if bom_line:
                vals.update({'bom_line_id': bom_line[0].id})
            stock_move = self.env['stock.move'].create(vals)
            stock_move._action_assign()
            stock_move._set_quantity_done(product_qty)
            stock_move._action_done()
        return True
