import logging

from datetime import datetime, timedelta
from odoo import models, fields, api, _

_logger = logging.getLogger("Shopify")


class CommonLogBookEpt(models.Model):
    _inherit = "common.log.book.ept"

    shopify_instance_id = fields.Many2one("shopify.instance.ept", "Instance")

    def create_crash_queue_schedule_activity(self, queue_id, model_id, note):
        """
        this method is used to create a schedule activity for queue.
        @:parameter : queue_id : it is object of queue
        Author: Nilesh Parmar
        Date: 07 February 2020.
        task id : 160579
        @author: Maulik Barad as created common method for all queues on dated 17-Feb-2020.
        """
        mail_activity_obj = self.env['mail.activity']
        activity_type_id = queue_id and queue_id.shopify_instance_id.shopify_activity_type_id.id
        date_deadline = datetime.strftime(
            datetime.now() + timedelta(days=int(queue_id.shopify_instance_id.shopify_date_deadline)),
            "%Y-%m-%d")
        if queue_id:
            for user_id in queue_id.shopify_instance_id.shopify_user_ids:
                mail_activity = mail_activity_obj.search(
                    [('res_model_id', '=', model_id), ('user_id', '=', user_id.id), ('res_id', '=', queue_id.id),
                     ('activity_type_id', '=', activity_type_id)])
                if not mail_activity:
                    vals = {'activity_type_id': activity_type_id,
                            'note': note,
                            'res_id': queue_id.id,
                            'user_id': user_id.id or self._uid,
                            'res_model_id': model_id,
                            'date_deadline': date_deadline}
                    try:
                        mail_activity_obj.create(vals)
                    except:
                        _logger.info("Unable to create schedule activity, Please give proper "
                                     "access right of this user :%s  " % user_id.name)
                        pass
        return True


class CommonLogLineEpt(models.Model):
    _inherit = "common.log.lines.ept"
    shopify_product_data_queue_line_id = fields.Many2one("shopify.product.data.queue.line.ept",
                                                         "Product Queue Line")
    shopify_order_data_queue_line_id = fields.Many2one("shopify.order.data.queue.line.ept",
                                                       "Order Queue Line")
    shopify_customer_data_queue_line_id = fields.Many2one("shopify.customer.data.queue.line.ept",
                                                       "Customer Queue Line")

    def shopify_create_product_log_line(self, message, model_id, queue_line_id, log_book_id):
        """This method used to create a log line.
            @param : self, comman_log_id, message,model_id, import_data_id
            @return: log_line
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 22/10/2019.
        """
        vals = {'message':message,
                'model_id':model_id,
                'res_id':queue_line_id.id if queue_line_id else False,
                'shopify_product_data_queue_line_id':queue_line_id.id if queue_line_id else False,
                'log_line_id' : log_book_id.id if log_book_id else False
                }
        log_line = self.create(vals)
        return log_line

    def shopify_create_order_log_line(self, message, model_id, queue_line_id, log_book_id):
        """This method used to create a log line.
            @param : self, message, model_id, queue_line_id
            @return: log_line
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 11/11/2019.
        """
        vals = {'message':message,
                'model_id':model_id,
                'res_id':queue_line_id and queue_line_id.id or False,
                'shopify_order_data_queue_line_id':queue_line_id and queue_line_id.id or False,
                'log_line_id': log_book_id.id if log_book_id else False,
                }
        log_line = self.create(vals)
        return log_line

    def shopify_create_customer_log_line(self, message, model_id, queue_line_id, log_book_id):
        vals = {'message': message,
                'model_id': model_id,
                'res_id': queue_line_id and queue_line_id.id or False,
                'shopify_customer_data_queue_line_id': queue_line_id and queue_line_id.id or False,
                'log_line_id': log_book_id.id if log_book_id else False,
                }
        log_line = self.create(vals)
        return log_line

