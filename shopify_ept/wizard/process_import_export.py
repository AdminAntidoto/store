import json
import logging
import time

from datetime import datetime, timedelta

from odoo.exceptions import Warning
from odoo.tools.misc import split_every

from odoo import models, fields, api, _
from .. import shopify

_logger = logging.getLogger("Shopify")


class ShopifyProcessImportExport(models.TransientModel):
    _name = 'shopify.process.import.export'
    _description = 'Shopify Process Import Export'

    shopify_instance_id = fields.Many2one(
        'shopify.instance.ept', string='Instance')
    sync_product_from_shopify = fields.Boolean("Sync Products")
    shopify_operation = fields.Selection(
        [
            ('sync_product',
             'Sync New Products - Set To Queue'),
            ('sync_product_by_remote_ids',
             'Sync New Products - By Remote Ids'),
            ('import_orders',
             'Import Orders'),
            ('import_orders_by_remote_ids',
             'Import Orders - By Remote Ids'),
            ('update_order_status',
             'Update Order Status'),
            ('import_customers',
             'Import Customers'),
            ('export_stock',
             'Export Stock'),
            ('import_stock',
             'Import Stock'),
            ('update_order_status',
             'Update Order Status'),
            ('import_payout_report',
             'Import Payout Report'),
        ],
        string="Operation",
        default="sync_product")
    orders_from_date = fields.Datetime(string="From Date")
    orders_to_date = fields.Datetime(string="To Date")
    shopify_instance_ids = fields.Many2many(
        "shopify.instance.ept",
        'shopify_instance_import_export_rel',
        'process_id',
        'shopify_instance_id',
        "Instances")
    shopify_is_set_price = fields.Boolean(string="Set Price ?",
                                          help="If is a mark, it set the price with product in the Shopify store.",
                                          default=False)
    shopify_is_set_stock = fields.Boolean(string="Set Stock ?",
                                          help="If is a mark, it set the stock with product in the Shopify store.",
                                          default=False)
    shopify_is_publish = fields.Selection(
        [('publish_product', 'Publish'), ('unpublish_product', 'Unpublish')],
        string="Publish In Website ?",
        help="If is a mark, it publish the product in website.",
        default='publish_product')
    shopify_is_set_image = fields.Boolean(string="Set Image ?",
                                          help="If is a mark, it set the image with product in the Shopify store.",
                                          default=False)
    shopify_is_set_basic_detail = fields.Boolean(string="Set Basic Detail ?",
                                                 help="If is a mark, it set the product basic detail in shopify store",
                                                 default=True)
    shopify_is_update_basic_detail = fields.Boolean(string="Update Basic Detail ?",
                                                    help="If is a mark, it update the product basic detail in shopify store",
                                                    default=False)
    shopify_is_update_price = fields.Boolean(string="set Price ?")
    shopify_template_ids = fields.Text(string="Template Ids",
                                       help="Based on template ids get product from shopify and import products in odoo")
    shopify_order_ids = fields.Text(string="Order Ids",
                                       help="Based on template ids get product from shopify and import products in odoo")
    export_stock_from = fields.Datetime(help="It is used for exporting stock from Odoo to Shopify.")
    payout_start_date = fields.Date(string='Start Date')
    payout_end_date = fields.Date(string='End Date')

    def shopify_execute(self):
        """This method used to execute the operation as per given in wizard.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 25/10/2019.
        """
        product_data_queue_obj = self.env["shopify.product.data.queue.ept"]
        order_date_queue_obj = self.env["shopify.order.data.queue.ept"]

        instance = self.shopify_instance_id
        if self.shopify_operation == 'sync_product':
            product_queues = product_data_queue_obj.shopify_create_product_data_queue(instance)
            if product_queues:
                action = self.env.ref('shopify_ept.action_shopify_product_data_queue').read()[0]
                action['domain'] = [('id', 'in', product_queues)]
                return action
        if self.shopify_operation == 'sync_product_by_remote_ids':
            product_queues = product_data_queue_obj.shopify_create_product_data_queue(instance,
                                                                                      self.shopify_template_ids)
            if product_queues:
                product_data_queue = product_data_queue_obj.browse(product_queues)
                product_data_queue.product_data_queue_lines.process_product_queue_line_data()
                _logger.info(
                    "Processed product queue : {0} of Instance : {1} Via Product Template ids Suuceessfully .".format(
                        product_data_queue.name,
                        instance.name))
                if not product_data_queue.product_data_queue_lines:
                    product_data_queue.unlink()
        if self.shopify_operation == 'import_customers':
            customer_queues = self.sync_shopify_customers()
            if customer_queues:
                action = self.env.ref('shopify_ept.action_shopify_synced_customer_data').read()[0]
                action['domain'] = [('id', 'in', customer_queues)]
                return action
        if self.shopify_operation == 'import_orders':
            order_queues = order_date_queue_obj.shopify_create_order_data_queues(instance,
                                                                                 self.orders_from_date,
                                                                                 self.orders_to_date)
            if order_queues:
                action = self.env.ref('shopify_ept.action_shopify_order_data_queue_ept').read()[0]
                action['domain'] = [('id', 'in', order_queues)]
                return action
        if self.shopify_operation == 'import_orders_by_remote_ids':
            order_date_queue_obj.import_order_process_by_remote_ids(instance, self.shopify_order_ids)
        if self.shopify_operation == 'export_stock':
            self.update_stock_in_shopify()
        if self.shopify_operation == 'import_stock':
            self.import_stock_in_odoo()
        if self.shopify_operation == 'update_order_status':
            self.update_order_status_in_shopify(instance=False)
        if self.shopify_operation=='import_payout_report':
            if self.payout_end_date and self.payout_start_date:
                if self.payout_end_date < self.payout_start_date:
                    raise Warning('The start date must be precede its end date')
                self.env['shopify.payout.report.ept'].get_payout_report(self.payout_start_date, self.payout_end_date,instance)
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def manual_export_product_to_shopify(self):
        start = time.time()
        shopify_product_template_obj = self.env['shopify.product.template.ept']
        shopify_product_obj = self.env['shopify.product.product.ept']
        shopify_products = self._context.get('active_ids', [])
        template = shopify_product_template_obj.browse(shopify_products)
        templates = template.filtered(lambda x: x.exported_in_shopify != True)
        if templates and len(templates) > 80:
            raise Warning("Error:\n- System will not export more then 80 Products at a "
                          "time.\n- Please select only 80 product for export.")

        if templates:
            shopify_product_obj.shopify_export_products(templates.shopify_instance_id,
                                                        self.shopify_is_set_price,
                                                        self.shopify_is_set_image,
                                                        self.shopify_is_publish,
                                                        self.shopify_is_set_basic_detail,
                                                        templates)
        end = time.time()
        _logger.info(
            "Export Processed %s Products in %s seconds." % (
                str(len(template)), str(end - start)))
        return True

    def manual_update_product_to_shopify(self):
        if not self.shopify_is_update_basic_detail and not self.shopify_is_publish and not self.shopify_is_set_price and not self.shopify_is_set_image:
            raise Warning("Please Select Any Option To Update Product")
        start = time.time()
        shopify_product_template_obj = self.env['shopify.product.template.ept']
        shopify_product_obj = self.env['shopify.product.product.ept']
        shopify_products = self._context.get('active_ids', [])
        template = shopify_product_template_obj.browse(shopify_products)
        templates = template.filtered(lambda x: x.exported_in_shopify)
        if templates and len(templates) > 80:
            raise Warning("Error:\n- System will not update more then 80 Products at a "
                          "time.\n- Please select only 80 product for export.")
        if templates:
            shopify_product_obj.update_products_in_shopify(templates.shopify_instance_id,
                                                           self.shopify_is_set_price,
                                                           self.shopify_is_set_image,
                                                           self.shopify_is_publish,
                                                           self.shopify_is_update_basic_detail,
                                                           templates)
        end = time.time()
        _logger.info(
            "Update Processed %s Products in %s seconds." % (
                str(len(template)), str(end - start)))
        return True

    def shopify_export_variant_vals(self, instance, variant, shopify_template):
        """This method used prepare a shopify template vals for export product process,
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 17/10/2019.
        """
        shopify_variant_vals = {
            'shopify_instance_id': instance.id,
            'product_id': variant.id,
            'shopify_template_id': shopify_template.id,
            'default_code': variant.default_code,
            'name': variant.name,
        }
        return shopify_variant_vals

    def shopify_export_template_vals(self, instance, odoo_template):
        """This method used prepare a shopify template vals for export product process,
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 17/10/2019.
        """
        shopify_template_vals = {
            'shopify_instance_id': instance.id,
            'product_tmpl_id': odoo_template.id,
            'name': odoo_template.name,
            'description': odoo_template.description_sale,
            'shopify_product_category': odoo_template.categ_id.id,
        }
        return shopify_template_vals

    ######################## Below methods created by Angel Patel ########################

    def sync_shopify_customers(self):
        """This method used to sync the customers data from Shopify to Odoo.
            @param : self
            @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 23/10/2019.
            :Task ID: 157065
        """
        self.shopify_instance_id.connect_in_shopify()
        if not self.shopify_instance_id.shopify_last_date_customer_import:
            customer_ids = shopify.Customer().search(limit=200)
            _logger.info("Imported first 200 Customers.")
            if len(customer_ids) >= 200:
                customer_ids = self.shopify_list_all_customer(customer_ids)
        else:
            customer_ids = shopify.Customer().find(
                updated_at_min=self.shopify_instance_id.shopify_last_date_customer_import)
            if len(customer_ids) >= 200:
                customer_ids = self.shopify_list_all_customer(customer_ids)
        if customer_ids:
            self.shopify_instance_id.shopify_last_date_customer_import = datetime.now()
        if not customer_ids:
            _logger.info(
                'Customers not found in result while the import customers from Shopify')
            return False
        _logger.info('Synced Customers len {}'.format(len(customer_ids)))
        # vals = {
        #     'shopify_instance_id': self.shopify_instance_id and self.shopify_instance_id.id or False,
        #     'state': 'draft',
        #     'record_created_from': 'import_process'
        # }
        customer_queue_list = []
        data_queue = self.env['shopify.customer.data.queue.ept']

        if len(customer_ids) > 0:
            # vals.update({'total_record_count': len(customer_ids)})

            if len(customer_ids) > 150:
                for customer_id_chunk in split_every(150, customer_ids):
                    customer_queue_id = data_queue.shopify_create_customer_queue(self.shopify_instance_id, "import_process")
                    customer_queue = self.shopify_create_multi_queue(customer_queue_id, customer_id_chunk)
                    customer_queue_list.append(customer_queue.id)
            else:
                customer_queue_id = data_queue.shopify_create_customer_queue(self.shopify_instance_id, "import_process")
                customer_queue = self.shopify_create_multi_queue(customer_queue_id, customer_ids)
                customer_queue_list.append(customer_queue.id)
        return customer_queue_list

    def shopify_create_multi_queue(self, customer_queue_id, customer_ids):
        """Create customer queue and queue line as per the requirement.
        @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 23/10/2019.
        :Task ID: 157065
        :param customer_queue_id:
        :param customer_ids:
        :return: True
        Modify Haresh Mori on date 26/12/2019 modification is changing the variable name.
        """
        # synced_shopify_customers_data_obj = self.env['shopify.customer.data.queue.ept']
        # synced_shopify_customers_line_obj = self.env['shopify.customer.data.queue.line.ept']
        # customer_queue_id = synced_shopify_customers_data_obj.create(vals)
        # customer_queue_id = self.shopify_customer_data_queue_create(vals)
        if customer_queue_id:
            for result in customer_ids:
                result = result.to_dict()
                self.shopify_customer_data_queue_line_create(result, customer_queue_id)
                # id = result.get('id')
                # name = "%s %s" % (result.get('first_name') or '', result.get('last_name') or '')
                # data = json.dumps(result)
                # line_vals = {
                #     'synced_customer_queue_id':customer_queue_id.id,
                #     'shopify_customer_data_id':id or '',
                #     'state':'draft',
                #     'name':name.strip(),
                #     'shopify_synced_customer_data':data,
                #     'shopify_instance_id':self.shopify_instance_id.id,
                #     'last_process_date':datetime.now(),
                # }
                # synced_shopify_customers_line_obj.create(line_vals)
        return customer_queue_id

    def shopify_customer_data_queue_line_create(self, result, customer_queue_id):
        """
        This method is used for create customer queue line using the result param and customer_queue_id.
        :param result:
        :param customer_queue_id:
        :return:
        @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 13/01/2020.
        """
        synced_shopify_customers_line_obj = self.env['shopify.customer.data.queue.line.ept']
        id = result.get('id')
        name = "%s %s" % (result.get('first_name') or '', result.get('last_name') or '')
        data = json.dumps(result)
        line_vals = {
            'synced_customer_queue_id': customer_queue_id.id,
            'shopify_customer_data_id': id or '',
            'state': 'draft',
            'name': name.strip(),
            'shopify_synced_customer_data': data,
            'shopify_instance_id': self.shopify_instance_id.id,
            'last_process_date': datetime.now(),
        }
        synced_shopify_customers_line_obj.create(line_vals)

    def webhook_customer_create_process(self, res, instance):
        """
        This method is used for create customer queue and queue line while the customer create form the webhook method.
        :param res:
        :param instance:
        :return:
        @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 13/01/2020.
        """
        res_partner_ept = self.env['shopify.res.partner.ept']
        data_queue = self.env['shopify.customer.data.queue.ept']
        customer_queue_id = data_queue.shopify_create_customer_queue(instance, "webhook")
        self.shopify_customer_data_queue_line_create(res, customer_queue_id)
        _logger.info(
            "process end : shopify odoo webhook for customer route call and customer queue is %s" % customer_queue_id.name)
        customer_queue_id.synced_customer_queue_line_ids.sync_shopify_customer_into_odoo()
        res_partner_obj = res_partner_ept.search([('shopify_customer_id', '=', res.get('id'))], limit=1)
        res_partner_obj.partner_id.update({
            'type': 'invoice'
        })

    def shopify_list_all_customer(self, result):
        """
            This method used to call the page wise data import for customers from Shopify to Odoo.
            @param : self,result
            @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 14/10/2019.
            :Task ID: 157065
            Modify by Haresh Mori on date 26/12/2019, Taken Changes for the pagination and API version.
        """
        sum_cust_list = []
        catch = ""
        while result:
            page_info = ""
            sum_cust_list += result
            link = shopify.ShopifyResource.connection.response.headers.get('Link')
            if not link or not isinstance(link, str):
                return sum_cust_list
            for page_link in link.split(','):
                if page_link.find('next') > 0:
                    page_info = page_link.split(';')[0].strip('<>').split('page_info=')[1]
                    try:
                        result = shopify.Customer().find(page_info=page_info, limit=200)
                        _logger.info("Imported next 200 Customers.")
                    except Exception as e:
                        if e.response.code == 429 and e.response.msg == "Too Many Requests":
                            time.sleep(5)
                            result = shopify.Customer().find(page_info=page_info, limit=200)
                        else:
                            raise Warning(e)
            if catch == page_info:
                break
        return sum_cust_list

    @api.model
    def update_stock_in_shopify(self, ctx={}):
        """
            This method used to export inventory stock from odoo to shopify.
            @param : self
            @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 09/11/2019.
            :Task ID: 157407
        :return:
        """
        if self.shopify_instance_id:
            instance = self.shopify_instance_id
        elif ctx.get('shopify_instance_id'):
            instance_id = ctx.get('shopify_instance_id')
            instance = self.env['shopify.instance.ept'].browse(instance_id)

        product_obj = self.env['product.product']
        shopify_product_obj = self.env['shopify.product.product.ept']

        if self.export_stock_from:
            last_update_date = self.export_stock_from
            _logger.info("Exporting Stock from Operations wizard for instance - %s....." % instance.name)
        else:
            last_update_date = instance.shopify_last_date_update_stock or datetime.now() - timedelta(30)
            _logger.info("Exporting Stock by Cron for instance - %s....." % instance.name)

        products = product_obj.get_products_based_on_movement_date(last_update_date,
                                                                   instance.shopify_company_id)
        if products:
            product_id_array = sorted(list(map(lambda x: x['product_id'], products)))
            product_id_array and shopify_product_obj.export_stock_in_shopify(instance,
                                                                             product_id_array)
        else:
            _logger.info("No products to export stock.....")
        return True

    def shopify_selective_product_stock_export(self):
        shopify_product_template_ids = self._context.get('active_ids')
        shopify_instance_ids = self.env['shopify.instance.ept'].search([])
        for instance_id in shopify_instance_ids:
            product_id = self.env['shopify.product.product.ept'].search(
                [('shopify_instance_id', '=', instance_id.id),
                 ('shopify_template_id', 'in', shopify_product_template_ids)]).product_id.ids
            if product_id:
                self.env['shopify.product.product.ept'].export_stock_in_shopify(instance_id,
                                                                                product_id)

    def import_stock_in_odoo(self):
        """
        Import stock from shopify to odoo
        import_shopify_stock method write in shopify_product_ept.py file
        :return: 157905
        """
        instance = self.shopify_instance_id
        shopify_product_obj = self.env['shopify.product.product.ept']
        shopify_product_obj.import_shopify_stock(instance)

    def update_order_status_in_shopify(self, instance=False):
        """
        Update order status function call from here
        update_order_status_in_shopify method write in sale_order.py
        :param instance:
        :return:
        @author: Angel Patel @Emipro Technologies Pvt.
        :Task ID: 157905
        """
        if not instance:
            instance = self.shopify_instance_id
        if instance.active:
            _logger.info(_("Your current active instance is '%s'") % instance.name)
            self.env['sale.order'].update_order_status_in_shopify(instance)
        else:
            _logger.info(_("Your current instance '%s' is in active.") % instance.name)

    def update_order_status_cron_action(self, ctx={}):
        """
        Using cron update order status
        :param ctx:
        :return:
        @author: Angel Patel @Emipro Technologies Pvt.
        :Task ID: 157716
        """
        instance_id = ctx.get('shopify_instance_id')
        instance = self.env['shopify.instance.ept'].browse(instance_id)
        _logger.info(
            _(
                "Auto cron update order status process start with instance: '%s'") % instance.name)
        self.update_order_status_in_shopify(instance)

    @api.onchange("shopify_instance_id")
    def onchange_shopify_order_date(self):
        """
        Author: Bhavesh Jadav 23/12/2019 for set fom date  instance wise
        :return:
        """
        instance = self.shopify_instance_id or False
        if instance:
            self.orders_from_date = instance.last_date_order_import or False
            self.orders_to_date = datetime.now()
            self.export_stock_from = instance.shopify_last_date_update_stock or datetime.now() - timedelta(30)
