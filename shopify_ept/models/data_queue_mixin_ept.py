from odoo import models


class DataQueueMixinEpt(models.AbstractModel):
    """ Mixin class for delete unused data queue from database."""
    _inherit = 'data.queue.mixin.ept'

    def delete_data_queue_ept(self, queue_data=[]):
        """
        This method will delete completed data queues from database.
        @author: Keyur Kanani
        :return: True
        """
        state = ('completed', 'done')
        days = 5
        queue_data.append({'table': 'shopify_product_data_queue_ept', 'state': state, 'days': days})
        queue_data.append({'table': 'shopify_product_data_queue_line_ept', 'state': state, 'days': days})
        queue_data.append({'table': 'shopify_order_data_queue_ept', 'state': state, 'days': days})
        queue_data.append({'table': 'shopify_order_data_queue_line_ept', 'state': state, 'days': days})
        queue_data.append({'table': 'shopify_customer_data_queue_ept', 'state': state, 'days': days})
        queue_data.append({'table': 'shopify_customer_data_queue_line_ept', 'state': state, 'days': days})
        return super(DataQueueMixinEpt, self).delete_data_queue_ept(queue_data)
