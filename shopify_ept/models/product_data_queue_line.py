import json
import logging
from datetime import datetime, timedelta

from odoo import models, fields
from .. import shopify

_logger = logging.getLogger("Shopify queue logger===(Emipro): ")


class ShopifyProductDataqueueLineEpt(models.Model):
    _name = "shopify.product.data.queue.line.ept"
    _description = 'Shopify Product Data Queue Line Ept'

    shopify_instance_id = fields.Many2one('shopify.instance.ept', string='Instance')
    last_process_date = fields.Datetime('Last Process Date', readonly=True)
    synced_product_data = fields.Text(string='Synced Product Data')
    product_data_id = fields.Char(string='Product Data Id')
    state = fields.Selection([('draft', 'Draft'), ('failed', 'Failed'), ('done', 'Done'),
                              ("cancel", "Cancelled")],
                             default='draft')
    product_data_queue_id = fields.Many2one('shopify.product.data.queue.ept',
                                            string='Product Data Queue', required=True,
                                            ondelete='cascade', copy=False)
    common_log_lines_ids = fields.One2many("common.log.lines.ept",
                                           "shopify_product_data_queue_line_id",
                                           help="Log lines created against which line.")
    name = fields.Char(string="Product", help="It contain the name of product")

    def auto_start_child_process_for_product_queue(self):
        """This method used to start the child process cron for process the product queue line data.
            @param : self
            @return: True
            @author: Haresh Mori @Emipro Technologies Pvt.Ltd on date 25/10/2019.
        """
        child_product_cron = self.env.ref('shopify_ept.ir_cron_child_to_process_product_queue_line')
        if child_product_cron and not child_product_cron.active:
            results = self.search([('state', '=', 'draft')], limit=100)
            if not results:
                return True
            child_product_cron.write({'active': True,
                                      'numbercall': 1,
                                      'nextcall': datetime.now() + timedelta(seconds=10)
                                      })
        return True

    def auto_import_product_queue_line_data(self):
        """- This method used to process synced shopify product data in batch of 100 queue lines.
           - This method is called from cron job.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt.Ltd on date 05/10/2019.
            Task_id : 157110
        """
        # change by bhavesh jadav 03/12/2019 for process  only one queue data at a time
        # query = """select product_data_queue_id from shopify_product_data_queue_line_ept where state='draft' ORDER BY create_date ASC limit 1"""
        query = """select queue.id
                from shopify_product_data_queue_line_ept as queue_line
                inner join shopify_product_data_queue_ept as queue on queue_line.product_data_queue_id = queue.id
                where queue_line.state='draft' and queue.is_action_require = 'False'
                ORDER BY queue_line.create_date ASC limit 1"""
        self._cr.execute(query)
        product_data_queue_id = self._cr.fetchone()
        if not product_data_queue_id:
            return

        queue = self.env['shopify.product.data.queue.ept'].browse(product_data_queue_id)
        product_data_queue_line_ids = queue.product_data_queue_lines
        # For counting the queue crashes and creating schedule activity for the queue.
        queue.queue_process_count += 1
        if queue.queue_process_count > 3:
            queue.is_action_require = True
            note = "<p>Attention %s queue is processed 3 times you need to process it manually.</p>" % (queue.name)
            queue.message_post(body=note)
            if queue.shopify_instance_id.is_shopify_create_schedule:
                model_id = self.env['ir.model'].search([('model', '=', 'shopify.product.data.queue.ept')]).id
                self.create_crash_queue_schedule_activity(queue, model_id, note)
            return
        self._cr.commit()
        product_data_queue_line_ids.process_product_queue_line_data()

    def create_product_queue_schedule_activity(self, queue_id):
        """
                this method is used to create a schedule activity for queue.
                @:parameter : queue_id : it is object of queue
                Author: Nilesh Parmar
                Date: 07 February 2020.
                task id : 160579
                :return:
                """
        mail_activity_obj = self.env['mail.activity']
        ir_model_obj = self.env['ir.model']
        model_id = ir_model_obj.search([('model', '=', 'shopify.product.data.queue.ept')])
        note = "Attention %s queue is processed 3 times you need to process it manually" % (queue_id.name)
        activity_type_id = queue_id and queue_id.shopify_instance_id.shopify_activity_type_id.id
        date_deadline = datetime.strftime(
            datetime.now() + timedelta(days=int(queue_id.shopify_instance_id.shopify_date_deadline)),
            "%Y-%m-%d")
        if queue_id:
            for user_id in queue_id.shopify_instance_id.shopify_user_ids:
                mail_activity = mail_activity_obj.search(
                    [('res_model_id', '=', model_id.id), ('user_id', '=', user_id.id), ('res_name', '=', queue_id.name),
                     ('activity_type_id', '=', activity_type_id)])
                note_2 = "<p>" + note + '</p>'
                if not mail_activity:
                    vals = {'activity_type_id': activity_type_id,
                            'note': note,
                            'res_id': queue_id.id,
                            'user_id': user_id.id or self._uid,
                            'res_model_id': model_id.id,
                            'date_deadline': date_deadline}
                    try:
                        mail_activity_obj.create(vals)
                    except:
                        pass
            return True

    def process_product_queue_line_data(self):
        """
            -This method processes product queue lines.
             @param : self
             @author: Haresh Mori @Emipro Technologies Pvt.Ltd on date 05/10/2019.
             Task_id : 157110
         """
        shopify_product_template_obj = self.env['shopify.product.template.ept']
        comman_log_obj = self.env["common.log.book.ept"]
        shopify_tmpl_id = False

        queue_id = self.product_data_queue_id if len(self.product_data_queue_id) == 1 else False
        if queue_id:
            # Below three line add by haresh mori on data 21/1/2020. To bypass the process when
            # the instance is not active.
            if not queue_id.shopify_instance_id.active:
                _logger.info("Instance '{}' is not active.".format(queue_id.shopify_instance_id.name))
                return True
            if queue_id.common_log_book_id:
                log_book_id = queue_id.common_log_book_id
            else:
                log_book_id = comman_log_obj.create({'type': 'import',
                                                     'module': 'shopify_ept',
                                                     'shopify_instance_id': queue_id.shopify_instance_id.id,
                                                     'active': True})
            # below two line add by Dipak Gogiya on date 15/01/2020, this is used to update
            # is_process_queue as False.
            self.env.cr.execute(
                """update shopify_product_data_queue_ept set is_process_queue = False where is_process_queue = True""")
            self._cr.commit()
            commit_count = 0
            for product_queue_line in self:
                commit_count += 1
                if commit_count == 10:
                    # Added by Dipak gogiya
                    queue_id.is_process_queue = True
                    self._cr.commit()
                    commit_count = 0
                shopify_product_template_obj.shopify_sync_products(product_queue_line,
                                                                   shopify_tmpl_id,
                                                                   product_queue_line.shopify_instance_id,
                                                                   log_book_id)
                # Below two-line add by Dipak Gogiya on date 15/01/2020 to manage the which queue is running in the background
                queue_id.is_process_queue = False
            queue_id.common_log_book_id = log_book_id
            # draft_or_failed_queue_line = self.filtered(lambda line: line.state in ['draft', 'failed'])
            # if draft_or_failed_queue_line:
            #     queue_id.write({'state': "partially_completed"})
            # else:
            #     queue_id.write({'state': "completed"})
            if queue_id.common_log_book_id and not queue_id.common_log_book_id.log_lines:
                queue_id.common_log_book_id.unlink()
            return True

    def replace_product_response(self):
        """ -This method used to replace the product data response in the failed queue line.It will
        call from the product queue line button.
             @param : self
             @author: Haresh Mori @Emipro Technologies Pvt.Ltd on date 21/1/2020.
         """

        if not self.shopify_instance_id.active:
            _logger.info("Instance '{}' is not active.".format(self.shopify_instance_id.name))
            return True
        self.shopify_instance_id.connect_in_shopify()
        if not self.product_data_id:
            return True
        result = shopify.Product().find(self.product_data_id)
        result = result.to_dict()
        data = json.dumps(result)
        self.write({'synced_product_data': data, 'state': 'draft'})
        self._cr.commit()
        self.process_product_queue_line_data()
        return True
