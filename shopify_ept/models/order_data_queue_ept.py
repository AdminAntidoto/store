from odoo import models, fields, api, _
from .. import shopify
from datetime import datetime, timedelta
import pytz, re
import logging

utc = pytz.utc
import time

_logger = logging.getLogger('shp_order_queue===(Emipro): ')


class ShopifyOrderDataQueueEpt(models.Model):
    _name = "shopify.order.data.queue.ept"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Shopify Order Data Queue EPT"

    name = fields.Char(help="Sequential name of imported order.", copy=False)
    shopify_instance_id = fields.Many2one('shopify.instance.ept', string='Instance',
                                          help="Order imported from this Shopify Instance.")
    state = fields.Selection([('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                              ('completed', 'Completed'), ('failed', 'Failed')],
                             default='draft', copy=False, compute="_compute_queue_state",
                             store=True)
    shopify_order_common_log_book_id = fields.Many2one("common.log.book.ept", help="""Related Log book which has
                                                                    all logs for current queue.""")
    shopify_order_common_log_lines_ids = fields.One2many(
        related="shopify_order_common_log_book_id.log_lines")
    order_data_queue_line_ids = fields.One2many("shopify.order.data.queue.line.ept",
                                                "shopify_order_data_queue_id")
    order_queue_line_total_record = fields.Integer(string='Total Records',
                                                   compute='_compute_order_queue_line_record')
    order_queue_line_draft_record = fields.Integer(string='Draft Records',
                                                   compute='_compute_order_queue_line_record')
    order_queue_line_fail_record = fields.Integer(string='Fail Records',
                                                  compute='_compute_order_queue_line_record')
    order_queue_line_done_record = fields.Integer(string='Done Records',
                                                  compute='_compute_order_queue_line_record')

    order_queue_line_cancel_record = fields.Integer(string='Cancel Records',
                                                    compute='_compute_order_queue_line_record')
    created_by = fields.Selection([("import", "By Manually Import Process"), ("webhook", "By Webhook"),
                                   ("scheduled_action", "By Scheduled Action")],
                                  help="Identify the process that generated a queue.", default="import")
    is_process_queue = fields.Boolean('Is Processing Queue', default=False)
    running_status = fields.Char(default="Running...")
    # order_log_lines = fields.One2many('common.log.lines.ept', 'order_queue_line_id', "log Lines")
    queue_process_count = fields.Integer(string="Queue Process Times",
                                         help="it is used know queue how many time processed")
    is_action_require = fields.Boolean(default=False, help="it is used  to find the action require queue")

    @api.depends('order_data_queue_line_ids.state')
    def _compute_queue_state(self):
        """
        Computes state from different states of queue lines.
        @author: Haresh Mori on Date 25-Dec-2019.
        """
        for record in self:
            if record.order_queue_line_total_record == record.order_queue_line_done_record + record.order_queue_line_cancel_record:
                record.state = "completed"
            elif record.order_queue_line_draft_record == record.order_queue_line_total_record:
                record.state = "draft"
            elif record.order_queue_line_total_record == record.order_queue_line_fail_record:
                record.state = "failed"
            else:
                record.state = "partially_completed"

    @api.depends('order_data_queue_line_ids.state')
    def _compute_order_queue_line_record(self):
        """This is used for count of total records of order queue lines.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 2/11/2019.
        """
        for order_queue in self:
            queue_lines = order_queue.order_data_queue_line_ids
            order_queue.order_queue_line_total_record = len(queue_lines)
            order_queue.order_queue_line_draft_record = len(queue_lines.filtered(lambda x: x.state == "draft"))
            order_queue.order_queue_line_done_record = len(queue_lines.filtered(lambda x: x.state == "done"))
            order_queue.order_queue_line_fail_record = len(queue_lines.filtered(lambda x: x.state == "failed"))
            order_queue.order_queue_line_cancel_record = len(queue_lines.filtered(lambda x: x.state == "cancel"))

    @api.model
    def create(self, vals):
        """This method used to create a sequence for Order Queue Data.
            @param : self,vals
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 04/11/2019.
        """
        sequence_id = self.env.ref('shopify_ept.seq_order_queue_data').ids
        if sequence_id:
            record_name = self.env['ir.sequence'].browse(sequence_id).next_by_id()
        else:
            record_name = '/'
        vals.update({'name': record_name or ''})
        return super(ShopifyOrderDataQueueEpt, self).create(vals)

    def import_order_cron_action(self, ctx={}):
        instance_id = ctx.get('shopify_instance_id')
        instance = self.env['shopify.instance.ept'].browse(instance_id)
        from_date = instance.last_date_order_import
        to_date = datetime.now()
        if not from_date:
            from_date = to_date - timedelta(3)

        self.shopify_create_order_data_queues(instance, from_date, to_date, created_by='scheduled_action')

    def shopify_create_order_data_queues(self, instance, from_date, to_date, created_by='import'):
        """This method used to create order data queues.
            @param : self, instance,  from_date, to_date
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 06/11/2019.
            Task Id : 157350
        """
        order_data_queue_line_boj = self.env["shopify.order.data.queue.line.ept"]
        instance.connect_in_shopify()
        order_queues = False
        order_ids = []
        instance.last_date_order_import = to_date
        for order_status_id in instance.import_shopify_order_status_ids:
            _logger.info("order_status_id %s"%(order_status_id.status))
            shopify_fulfillment_status = order_status_id.status
            if shopify_fulfillment_status == 'any' or shopify_fulfillment_status == 'shipped':
                order_ids = shopify.Order().find(status='any',
                                                  fulfillment_status=shopify_fulfillment_status,
                                                  updated_at_min=from_date,
                                                  updated_at_max=to_date, limit=250)                    
                _logger.info(order_ids)
                order_queues = order_data_queue_line_boj.create_order_data_queue_line(order_ids,
                                                                                      instance, created_by=created_by)
                _logger.info(order_queues)
                self._cr.commit()
                if len(order_ids) >= 50:
                    order_ids = self.list_all_orders(order_ids,instance,created_by)
            else:
                order_ids = shopify.Order().find(fulfillment_status=shopify_fulfillment_status,
                                                  updated_at_min=from_date,
                                                  updated_at_max=to_date, limit=250)

                order_queues = order_data_queue_line_boj.create_order_data_queue_line(order_ids,
                                                                                      instance, created_by=created_by)
                _logger.info(order_queues)
                self._cr.commit()
                if len(order_ids) >= 50:
                    order_ids = self.list_all_orders(order_ids,instance,created_by)
        _logger.info('Length of Shopify orders %s import from instance name: %s' % (
            len(order_ids), instance.name))
        return order_queues
    def list_all_orders(self, result,instance=False,created_by=False):
        """This method used to get the list of orders from Shopify to Odoo.
            @param : self, result, to_date, from_date, shopify_fulfillment_status
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 06/11/2019.
            Task_id : 157350
            Modify on date 27/12/2019 Taken pagination chnages
        """
        order_data_queue_line_boj = self.env["shopify.order.data.queue.line.ept"]
        sum_order_list = []
        catch = ""
        while result:
            page_info = ""
            sum_order_list += result
            link = shopify.ShopifyResource.connection.response.headers.get('Link')
            if not link or not isinstance(link, str):
                return sum_order_list
            for page_link in link.split(','):
                if page_link.find('next') > 0:
                    page_info = page_link.split(';')[0].strip('<>').split('page_info=')[1]
                    try:
                        result = shopify.Order().find(limit=250, page_info=page_info)
                        order_data_queue_line_boj.create_order_data_queue_line(result,instance, created_by=created_by)
                        self._cr.commit()
                    except Exception as e:
                        if e.response.code == 429 and e.response.msg == "Too Many Requests":
                            time.sleep(5)
                            result = shopify.Order().find(limit=250, page_info=page_info)
                            order_data_queue_line_boj.create_order_data_queue_line(result,instance, created_by=created_by)
                            self._cr.commit()

                        else:
                            raise Warning(e)
            if catch == page_info:
                break
        return sum_order_list


    def create_schedule_activity(self, queue_id):
        """
        Author : Bhavesh Jadav 28/11/2019 this method use for create schedule activity on order data queue based on queue line
        :model: model use for the model
        :return: True or False
        """
        mail_activity_obj = self.env['mail.activity']
        ir_model_obj = self.env['ir.model']
        model_id = ir_model_obj.search([('model', '=', 'shopify.order.data.queue.ept')])
        activity_type_id = queue_id and queue_id.shopify_instance_id.shopify_activity_type_id.id
        date_deadline = datetime.strftime(
            datetime.now() + timedelta(
                days=int(queue_id.shopify_instance_id.shopify_date_deadline)),
            "%Y-%m-%d")
        if queue_id:
            shopify_order_id_list = queue_id.order_data_queue_line_ids.filtered(
                lambda line: line.state == 'failed').mapped('shopify_order_id')
            if shopify_order_id_list and len(shopify_order_id_list) > 0:
                note = 'Your order has not been imported for Shopify Order Reference : %s' % str(
                    shopify_order_id_list)[1:-1]
                if note and shopify_order_id_list:
                    for user_id in queue_id.shopify_instance_id.shopify_user_ids:
                        mail_activity = mail_activity_obj.search(
                            [('res_model_id', '=', model_id.id), ('user_id', '=', user_id.id),
                             ('res_name', '=', queue_id.name),
                             ('activity_type_id', '=', activity_type_id)])
                        note_2 = "<p>" + note + '</p>'
                        if not mail_activity or mail_activity.note != note_2:
                            vals = {'activity_type_id': activity_type_id,
                                    'note': note,
                                    'res_id': queue_id.id,
                                    'user_id': user_id.id or self._uid,
                                    'res_model_id': model_id.id,
                                    'date_deadline': date_deadline}
                            try:
                                mail_activity_obj.create(vals)
                            except:
                                _logger.info(
                                    "Unable to create schedule activity, Please give proper "
                                    "access right of this user :%s  " % user_id.name)
                                pass
        return True

    def import_order_process_by_remote_ids(self, instance, order_ids):
        """
        This method is used for get a order from shopify based on order ids and create its queue and process it.
        :param instance: browsable object of shopify instance
        :param order_ids: It contain the comma separated ids of shopify orders and its type is String
        :return: It will return either True or False
        """
        if order_ids:
            instance.connect_in_shopify()
            # Below one line is used to find only character values from order ids.
            only_alphabets = re.findall("[a-zA-Z]+", order_ids)
            if len(order_ids.split(',')) <= 50:
                # order_ids_list is a list of all order ids which response did not given by shopify.
                order_ids_list = list(set(re.findall(re.compile(r"(\d+)"), order_ids)))
                results = shopify.Order().find(ids=','.join(order_ids_list), status='any')
                if results:
                    _logger.info('Length of Shopify orders %s import from instance name: %s' % (
                        len(results), instance.name))
                    order_ids_list = [order_id.strip() for order_id in order_ids_list]
                    # Below process to identify which id response did not give by Shopify.
                    [order_ids_list.remove(str(result.id)) for result in results if str(result.id) in order_ids_list]
            else:
                raise Warning(_('Please enter the Order ids 50 or less'))
            if results:
                order_queues = self.env["shopify.order.data.queue.line.ept"].create_order_data_queue_line(results,
                                                                                                          instance)
                order_data_queue = self.env['shopify.order.data.queue.ept'].browse(order_queues)
                if order_data_queue:
                    if order_ids_list or only_alphabets:
                        order_data_queue.message_post(
                            body="%s orders are not imported" % (','.join(order_ids_list + only_alphabets)))
                    order_data_queue.order_data_queue_line_ids.process_import_order_queue_data()
                    _logger.info(
                        "Imported order queue : {0} of Instance : {1} via Import shopify Remote Order ids Successfully".format(
                            order_data_queue.name, instance.name))
                _logger.info(
                    "Processed order queue : {0} of Instance : {1} via Import Remote Order Ids Successfully".format(
                        order_data_queue.name, instance.name))
                if not order_data_queue.order_data_queue_line_ids:
                    order_data_queue.unlink()
        return True
