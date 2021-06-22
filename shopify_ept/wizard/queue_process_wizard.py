from odoo import models, fields, api, _


class ShopifyQueueProcessEpt(models.TransientModel):
    _name = 'shopify.queue.process.ept'
    _description = 'Shopify Queue Process Ept'

    def manual_queue_process(self):
        queue_process = self._context.get('queue_process')
        if queue_process == "process_product_queue_manually":
            self.process_product_queue_manually()
        if queue_process == "process_customer_queue_manually":
            self.process_customer_queue_manually()
        if queue_process == "process_order_queue_manually":
            self.process_order_queue_manually()

    def process_product_queue_manually(self):
        """This method used to process the product queue manually. You can call the method from here :
            Shopify => Configuration => Product Queue Data => Action => Process Queue Manually.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 25/10/2019.
        """
        shopify_product_queue_line_obj = self.env["shopify.product.data.queue.line.ept"]
        product_queue_ids = self._context.get('active_ids')
        # below two line add by Dipak Gogiya on date 15/01/2020, this is used to update
        # is_process_queue as False.
#         self.env.cr.execute(
#             """update shopify_product_data_queue_ept set is_process_queue = False where is_process_queue = True""")
#         self._cr.commit()
        # Upper 2 lines are commented by Maulik Barad on dated 17-Feb-2020.
        for product_queue_id in product_queue_ids:
            product_queue_line_batch = shopify_product_queue_line_obj.search(
                    [("product_data_queue_id", "=", product_queue_id),
                     ("state", "in", ('draft', 'failed'))])
            product_queue_line_batch.process_product_queue_line_data()
        return True

    def process_customer_queue_manually(self):
        """This method used to read and create only selected customers data from "shopify.customer.data.queue.ept" model.
            @param : self
            @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 23/10/2019.
            :Task ID: 157065
        """
        customer_line_obj = self.env["shopify.customer.data.queue.line.ept"]
        synced_customer_queue_id = self._context.get('active_ids')
        customer_queue_id = self.env['shopify.customer.data.queue.ept'].browse(
                synced_customer_queue_id)
        if customer_queue_id.synced_customer_queue_line_ids:
            synced_customer_queue_line_ids = customer_queue_id.synced_customer_queue_line_ids.filtered(
                    lambda line:line.state == 'draft')
            if synced_customer_queue_line_ids:
                customer_line_obj.sync_shopify_customer_into_odoo(synced_customer_queue_line_ids)

    def process_order_queue_manually(self):
        """This method used to process the order queue manually. You can call the method from here :
            Shopify => Configuration => Order Queue Data => Action => Order Queue Manually.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 14/10/2019.
        """
        shopify_order_queue_line_obj = self.env["shopify.order.data.queue.line.ept"]
        order_queue_ids = self._context.get('active_ids')
        # Below two line add by Dipak Gogiya on date 15/01/2020, this is used to update
        # is_process_queue as False.
        self.env.cr.execute(
            """update shopify_order_data_queue_ept set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()
        for order_queue_id in order_queue_ids:
            order_queue_line_batch = shopify_order_queue_line_obj.search(
                    [("shopify_order_data_queue_id", "=", order_queue_id),
                     ("state", "in", ('draft', 'failed'))])
            order_queue_line_batch.process_import_order_queue_data()
        return True

    def set_to_completed_queue(self):
        """
        This method used to change the queue state as completed.
        Haresh Mori on date 25/Dec/2019
        """
        queue_process = self._context.get('queue_process')
        if queue_process == "set_to_completed_order_queue":
            self.set_to_completed_order_queue_manually()
        if queue_process == "set_to_completed_product_queue":
            self.set_to_completed_product_queue_manually()
        if queue_process == "set_to_completed_customer_queue":
            self.set_to_completed_customer_queue_manually()

    def set_to_completed_order_queue_manually(self):
        """This method used to set order queue as completed. You can call the method from here :
            Shopify => Data Queues => Order Data Queues => SET TO COMPLETED.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 25/12/2019.
        """
        order_queue_ids = self._context.get('active_ids')
        order_queue_ids = self.env['shopify.order.data.queue.ept'].browse(order_queue_ids)
        for order_queue_id in order_queue_ids:
            queue_lines = order_queue_id.order_data_queue_line_ids.filtered(
                    lambda line:line.state in ['draft', 'failed'])
            queue_lines.write({'state':'cancel'})
            order_queue_id.message_post(body=_("Manually set to cancel queue lines %s - ")
                                             % (queue_lines.mapped('shopify_order_id')))
        return True

    def set_to_completed_product_queue_manually(self):
        """This method used to set product queue as completed. You can call the method from here :
            Shopify => Data Queues => Product Data Queues => SET TO COMPLETED.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 25/12/2019.
        """
        product_queue_ids = self._context.get('active_ids')
        product_queue_ids = self.env['shopify.product.data.queue.ept'].browse(product_queue_ids)
        for product_queue_id in product_queue_ids:
            queue_lines = product_queue_id.product_data_queue_lines.filtered(
                    lambda line:line.state in ['draft', 'failed'])
            queue_lines.write({'state':'cancel'})
            product_queue_id.message_post(body=_("Manually set to cancel queue lines %s - ")
                                               % (queue_lines.mapped('product_data_id')))
        return True

    def set_to_completed_customer_queue_manually(self):
        """This method used to set customer queue as completed. You can call the method from here :
            Shopify => Data Queues => Customer Data Queues => SET TO COMPLETED.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 25/12/2019.
        """
        customer_queue_ids = self._context.get('active_ids')
        customer_queue_ids = self.env['shopify.customer.data.queue.ept'].browse(customer_queue_ids)
        for customer_queue_id in customer_queue_ids:
            queue_lines = customer_queue_id.synced_customer_queue_line_ids.filtered(
                    lambda line:line.state in ['draft', 'failed'])
            queue_lines.write({'state':'cancel'})
            # product_queue_id.message_post(body=_("Manually set to cancel queues %s") % (
            #     queue_lines.mapped('shopify_customer_data_id')))
        return True
