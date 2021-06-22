import time
import json, re
import logging
import pytz
from odoo import models, fields, api, _
from odoo.exceptions import Warning
from .. import shopify
from datetime import datetime, timedelta


_logger = logging.getLogger("shopify_product_queue===(Emipro): ")

class ShopifyProductDataqueue(models.Model):
    _name = "shopify.product.data.queue.ept"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Shopify Product Data Queue'

    name = fields.Char(size=120, string='Name')
    shopify_instance_id = fields.Many2one('shopify.instance.ept', string='Instance')
    state = fields.Selection([('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
                              ('completed', 'Completed'),('failed', 'Failed')], default='draft',
                             compute="_compute_queue_state",store = True)
    product_data_queue_lines = fields.One2many('shopify.product.data.queue.line.ept',
                                               'product_data_queue_id',
                                               string="Product Queue Lines")
    common_log_book_id = fields.Many2one("common.log.book.ept",
                                         help="""Related Log book which has all logs for current queue.""")
    common_log_lines_ids = fields.One2many(related="common_log_book_id.log_lines")
    queue_line_total_records = fields.Integer(string='Total Records',
                                              compute='_compute_queue_line_record')
    queue_line_draft_records = fields.Integer(string='Draft Records',
                                              compute='_compute_queue_line_record')
    queue_line_fail_records = fields.Integer(string='Fail Records',
                                             compute='_compute_queue_line_record')
    queue_line_done_records = fields.Integer(string='Done Records',
                                             compute='_compute_queue_line_record')
    queue_line_cancel_records = fields.Integer(string='Cancelled Records',
                                             compute='_compute_queue_line_record')
    created_by = fields.Selection([("import", "By Import Process"), ("webhook", "By Webhook")],
                                  help="Identify the process that generated a queue.",
                                  default="import")
    is_process_queue = fields.Boolean('Is Processing Queue', default=False)
    running_status = fields.Char(default="Running...")
    is_action_require = fields.Boolean(default=False)
    queue_process_count = fields.Integer(string="Queue Process Times",
                                         help="it is used know queue how many time processed")

    @api.depends('product_data_queue_lines.state')
    def _compute_queue_line_record(self):
        """This is used for count of total record of product queue line.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 2/11/2019.
        """
        for product_queue in self:
            queue_lines = product_queue.product_data_queue_lines
            product_queue.queue_line_total_records = len(queue_lines)
            product_queue.queue_line_draft_records = len(
                    queue_lines.filtered(lambda x:x.state == 'draft'))
            product_queue.queue_line_fail_records = len(
                    queue_lines.filtered(lambda x:x.state == 'failed'))
            product_queue.queue_line_done_records = len(
                    queue_lines.filtered(lambda x:x.state == 'done'))
            product_queue.queue_line_cancel_records = len(
                    queue_lines.filtered(lambda x:x.state == 'cancel'))

    @api.depends('product_data_queue_lines.state')
    def _compute_queue_state(self):
        """
        Computes state from different states of queue lines.
        @author: Haresh Mori on Date 25-Dec-2019.
        """
        for record in self:
            if record.queue_line_total_records == record.queue_line_done_records + record.queue_line_cancel_records:
                record.state = "completed"
            elif record.queue_line_draft_records == record.queue_line_total_records:
                record.state = "draft"
            elif record.queue_line_total_records == record.queue_line_fail_records:
                record.state = "failed"
            else:
                record.state = "partially_completed"

    @api.model
    def create(self, vals):
        """This method used to create a sequence for synced shopify data.
            @param : self,vals
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 05/10/2019.
        """
        sequence_id = self.env.ref('shopify_ept.seq_product_queue_data').ids
        if sequence_id:
            record_name = self.env['ir.sequence'].browse(sequence_id).next_by_id()
        else:
            record_name = '/'
        vals.update({'name':record_name or ''})
        return super(ShopifyProductDataqueue, self).create(vals)

    def shopify_create_product_data_queue(self, instance, template_ids=''):
        """This method used to create a product data queue while syncing product from Shopify to Odoo.
            @param : self, insatnce
            @return: True
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 25/10/2019.
            @modify: Dipak Gogiya @Emipro Technologies Pvt. Ltd on date 23/01/2020.
        """
        instance.connect_in_shopify()
        only_alphabets = []
        if template_ids:
            # Below one line is used to find only character values from template ids.
            only_alphabets = re.findall("[a-zA-Z]+", template_ids)
            if len(template_ids.split(',')) <= 50:
                # template_ids is a list of all template ids which response did not given by
                # shopify.
                template_ids = list(set(re.findall(re.compile(r"(\d+)"),template_ids)))
                results = shopify.Product().find(ids=','.join(template_ids))
                if results:
                    _logger.info('Length of Shopify Products %s import from instance name: %s' % (
                        len(results), instance.name))
                    template_ids = [template_id.strip() for template_id in template_ids]
                    # Below process to identify which id response did not give by Shopify.
                    [template_ids.remove(str(result.id)) for result in results if str(result.id) in template_ids]
            else:
                raise Warning(_('Please enter the product template ids 50 or less'))
        else:
            if not instance.shopify_last_date_product_import:
                results = shopify.Product().find(limit=250)
                if len(results) >= 250:
                    results = self.shopify_list_all_products(results)
                    #results = self.get_product(results)
            else:
                # updated_at_min =datetime.strptime(pytz.utc.localize(instance.shopify_last_date_product_import).astimezone(
                # pytz.timezone(instance.shopify_store_time_zone[12:] or 'UTC')).strftime(
                # '%Y-%m-%d %H:%M:%S'), "%Y-%m-%d %H:%M:%S")
                results = shopify.Product().find(updated_at_min=instance.shopify_last_date_product_import,limit=250) # Change by bhavesh jadav 13/12/2019 limit=250
                if len(results) >= 250:
                    results=self.shopify_list_all_products(results)
            if results:
                instance.shopify_last_date_product_import = datetime.now()
        if not results:
            _logger.info(
                    'No Products found to be imported from Shopify.')
            return False
        _logger.info('Total synced products - {}'.format(len(results)))
        count = 0
        one_time_create = True
        product_queue_list = []
        for result in results:
            if one_time_create:
                product_queue_id = self.shopify_create_product_queue(instance)
                product_queue_list.append(product_queue_id.id)
                _logger.info('Shopify Product Queue created. Queue name is  {}'.format(
                        product_queue_id.name))
                one_time_create = False
                if template_ids or only_alphabets:
                    product_queue_id.message_post(body="%s products are not imported" %(','.join(template_ids+only_alphabets)))
            self.shopify_create_product_data_queue_line(result, instance, product_queue_id)
            count = count + 1
            if count == 100:
                count = 0
                one_time_create = True
        return product_queue_list

    def shopify_list_all_updated_products(self,result,updated_at_min):
        """
        author: Bhavesh Jadav 13/12/2019 if updated product is more then 250 then you need to request with page 2
        result: use for the previous response result
        updated_at_min:last import product date
        """
        sum_of_result = result
        if not sum_of_result:
            return sum_of_result
        try:
            new_result = shopify.Product().find(limit=250,updated_at_min=updated_at_min,page=2)
        except Exception as e:
            if e.response.code == 429 and e.response.msg == "Too Many Requests":
                time.sleep(5)
                new_result = shopify.Product().find(limit=250, updated_at_min=updated_at_min, page=2)
            else:
                raise Warning(e)
        page_no = 2
        while new_result:
            page_no += 1
            sum_of_result = sum_of_result + new_result
            try:
                new_result = shopify.Product().find(limit=250, updated_at_min=updated_at_min,page=page_no)
            except Exception as e:
                if e.response.code == 429 and e.response.msg == "Too Many Requests":
                    time.sleep(5)
                    new_result = shopify.Product().find(limit=250,updated_at_min=updated_at_min, page=page_no)
                else:
                    raise Warning(e)
        return sum_of_result


    def shopify_list_all_products(self, result):
        """This method used to call the page wise data of product to import from Shopify to Odoo.
            @param : self,result
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 14/10/2019.
            Modify on date 27/12/2019 Taken pagination changes.
        """
        sum_product_list = []
        catch = ""
        while result:
            page_info = ""
            sum_product_list += result
            link = shopify.ShopifyResource.connection.response.headers.get('Link')
            if not link or not isinstance(link, str):
                return sum_product_list
            for page_link in link.split(','):
                if page_link.find('next') > 0:
                    page_info = page_link.split(';')[0].strip('<>').split('page_info=')[1]
                    try:
                        result = shopify.Product().find(page_info=page_info, limit=250)
                    except Exception as e:
                        if e.response.code == 429 and e.response.msg == "Too Many Requests":
                            time.sleep(5)
                            result = shopify.Product().find(page_info=page_info, limit=250)
                        else:
                            raise Warning(e)
            if catch == page_info:
                break
        return sum_product_list

    def shopify_create_product_queue(self, instance, created_by='import'):
        """This method used to create a product queue as per the split requirement of the
        queue. It is used for process the queue manually.
            @param : self, insatnce.
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 11/11/2019.
            @modify: Dipak Gogiya @Emipro Technologies Pvt. Ltd on date 10/01/2020.
            Task Id :
        """
        #Added created_by field which is used to identify the queue is created from which process import or webhook : Dipak Gogiya
        product_queue_vals = {
            'shopify_instance_id':instance and instance.id or False,
            'state':'draft',
            'created_by': created_by
        }
        product_queue_data_id = self.create(product_queue_vals)

        return product_queue_data_id

    def shopify_create_product_data_queue_line(self, result, instance, product_queue_data_id):
        """This method used to create a product data queue line.
            @param : self, result, insatnce, product_queue_data_id
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 25/10/2019.
        """
        product_data_queue_line_obj = self.env["shopify.product.data.queue.line.ept"]
        product_queue_line_vals = {}
        #doesn't need to convert the response into dictionary while response is getting from webhook [Add Changes] Dipak Gogiya
        if type(result) is not dict:
            result = result.to_dict()
        data = json.dumps(result)
        product_queue_line_vals.update({'product_data_id':result.get('id'),
                                        'shopify_instance_id':instance and instance.id or False,
                                        'synced_product_data':data,
                                        'name': result.get('title'),
                                        'product_data_queue_id':product_queue_data_id and product_queue_data_id.id or False,
                                        'state':'draft',
                                        })
        product_data_queue_line_obj.create(product_queue_line_vals)
        return True

    def create_schedule_activity_for_product(self, queue_line, from_sale=False):
        """
        author: Bhavesh Jadav 13/12/2019 for create schedule activity will product has extra attribute
        queue_line: is use for order queue_line or product queue_line
        from_sale:is use for identify its from sale process or product process
        """
        mail_activity_obj = self.env['mail.activity']
        ir_model_obj = self.env['ir.model']
        if from_sale:
            queue_id = queue_line.shopify_order_data_queue_id
            model_id = ir_model_obj.search([('model', '=', 'shopify.order.data.queue.ept')])
            data_ref = queue_line.shopify_order_id
            note = 'Your order has not been imported because of the product of order Has a new attribute  Shopify Order ' \
                   'Reference : %s' % data_ref
        else:
            queue_id = queue_line.product_data_queue_id
            model_id = ir_model_obj.search([('model', '=', 'shopify.product.data.queue.ept')])
            data_ref = queue_line.product_data_id
            note = 'Your product was not synced because you tried to add new attribute | Product Data Reference : %s' % data_ref
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
                duplicate_note = mail_activity.filter(lambda x: x.note == note_2)
                if not mail_activity or not duplicate_note:
                    vals = {'activity_type_id': activity_type_id,
                            'note': note,
                            'res_id': queue_id.id,
                            'user_id': user_id.id or self._uid,
                            'res_model_id': model_id.id,
                            'date_deadline': date_deadline}
                    try:
                        mail_activity_obj.create(vals)
                    except:
                        # _logger.info('Selected user have not rights to access order queue: %s' % user_id.name
                        pass
            return True

    def create_product_queue_from_webhook(self, product_data, instance):
        """
        This method used to create a product queue and its line from webhook response and
        also process it.
        @author: Dipak Gogiya on Date 10-Jan-2020.
        """
        product_data_queue = self.shopify_create_product_queue(instance, "webhook")
        self.shopify_create_product_data_queue_line(product_data, instance, product_data_queue)
        _logger.info(
            "Imported product {0} of {1} via Webhook Successfully.".format(product_data.get("id"),
                                                                           instance.name))

        product_data_queue.product_data_queue_lines.process_product_queue_line_data()
        _logger.info(
            "Processed product {0} of {1} via Webhook Successfully.".format(product_data.get("id"),
                                                                            instance.name))
