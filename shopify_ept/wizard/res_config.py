from odoo import models, fields, api, _
from odoo.exceptions import Warning
from .. import shopify


class ShopifyInstanceConfig(models.TransientModel):
    _name = 'res.config.shopify.instance'
    _description = 'Shopify Instance Configuration'

    name = fields.Char("Instance Name")
    shopify_api_key = fields.Char("API Key", required=True)
    shopify_password = fields.Char("Password", required=True)
    shopify_shared_secret = fields.Char("Secret Key", required=True)
    shopify_host = fields.Char("Host", required=True)
    shopify_country_id = fields.Many2one('res.country', string="Country", required=True)
    is_image_url = fields.Boolean("Is Image URL?",
                                  help="Check this if you use Images from URL\nKeep as it is if you use Product images")
    # apply_tax_in_order = fields.Selection(
    #     [("odoo_tax", "Odoo Default Tax Behaviour"), ("create_shopify_tax",
    #                                                   "Create New Tax If Not Found")],
    #     copy=False, help=""" For Shopify Orders :- \n
    #                 1) Odoo Default Tax Behaviour - The Taxes will be set based on Odoo's
    #                              default functional behaviour i.e. based on Odoo's Tax and Fiscal Position configurations. \n
    #                 2) Create New Tax If Not Found - System will search the tax data received
    #                 from Shopify in Odoo, will create a new one if it fails in finding it.""")
    # invoice_tax_account_id = fields.Many2one('account.account', string='Invoice Tax '
    #                                                                    'Account')
    # credit_tax_account_id = fields.Many2one('account.account', string='Credit Tax Account')

    def shopify_test_connection(self):
        """This method used to verify whether Odoo is capable of connecting with Shopify or not.
            @param : self
            @return : Action of type reload.
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 04/10/2019.
            Task Id:
        """
        instance_obj = self.env['shopify.instance.ept']
        instance_id = instance_obj.with_context(active_test=False).search(
            ['|', ('shopify_api_key', '=', self.shopify_api_key),
             ('shopify_host', '=', self.shopify_host)], limit=1)
        if instance_id:
            raise Warning(
                "An instance already exists for the given details \nShopify API key : '%s' \nShopify Host : '%s'" % (
                    self.shopify_api_key, self.shopify_host))

        shop = self.shopify_host.split("//")
        if len(shop) == 2:
            shop_url = shop[0] + "//" + self.shopify_api_key + ":" + self.shopify_password + "@" + \
                       shop[1] + "/admin/api/2020-01"
        else:
            shop_url = "https://" + self.shopify_api_key + ":" + self.shopify_password + "@" + shop[
                0] + "/admin/api/2020-01"
        shopify.ShopifyResource.set_site(shop_url)
        try:
            shop_id = shopify.Shop.current()
        except Exception as e:
            raise Warning(e)
        shop_detail = shop_id.to_dict()
        shop_currency = shop_detail.get('currency')
        global_channel_obj = self.env['global.channel.ept']
        pricelist_obj = self.env['product.pricelist']
        currency_obj = self.env['res.currency']
        currency_id = currency_obj.search([('name', '=', shop_currency)], limit=1)
        # company_id= False
        if not currency_id:
            currency_id = currency_obj.search([('name', '=', shop_currency), ('active', '=', False)], limit=1)
            currency_id.write({'active':True})
        if not currency_id:
            currency_id = self.env.user.currency_id
        price_list_name = self.name + ' ' + 'PriceList'
        pricelist_id = pricelist_obj.search([('name', '=', price_list_name), ('currency_id', '=', currency_id.id)],
                                            limit=1)  # ,('company_id','=',company_id)
        if not pricelist_id:
            pricelist_id = pricelist_obj.create({'name': price_list_name,
                                                 'currency_id': currency_id.id,
                                                 })  # 'company_id':company_id
        stock_field = self.env['ir.model.fields'].search(
            [('model_id.model', '=', 'product.product'), ('name', '=', 'qty_available')],
            limit=1)
        # shopify_global_channel_id = global_channel_obj.search([('name', '=', self.name),('shopify_instance_id','=',self.id)], limit=1)
        # if not shopify_global_channel_id:
        #     shopify_global_channel_id = global_channel_obj.create({'name': self.name,'shopify_instance_id':self.id})
        # instance_id = instance_obj.search(
        #     [('shopify_api_key', '=', self.shopify_api_key), ('shopify_host', '=', self.shopify_host)], limit=1)
        # if instance_id:
        #     raise Warning(
        #         "An instance already exists for the given details \nShopify API key : '%s' \nShopify Host : '%s'" % (
        #             self.shopify_api_key, self.shopify_host))
        vals = {
            'name': self.name,
            'shopify_api_key': self.shopify_api_key,
            'shopify_password': self.shopify_password,
            'shopify_shared_secret': self.shopify_shared_secret,
            'shopify_host': self.shopify_host,
            'shopify_country_id': self.shopify_country_id.id,
            'shopify_store_time_zone': shop_detail.get('timezone'),
            'shopify_pricelist_id': pricelist_id and pricelist_id.id or False,
            'apply_tax_in_order':'create_shopify_tax',
            'shopify_stock_field':stock_field and stock_field.id or False
            }
        shopify_instance = self.env['shopify.instance.ept'].create(vals)
        self.env['shopify.location.ept'].import_shopify_locations(shopify_instance)
        shopify_global_channel_id = global_channel_obj.search(
            [('name', '=', self.name), ('shopify_instance_id', '=', shopify_instance.id)], limit=1)
        if not shopify_global_channel_id:
            shopify_global_channel_id = global_channel_obj.create(
                {'name': self.name, 'shopify_instance_id': shopify_instance.id})
        shopify_instance.write({'shopify_global_channel_id': shopify_global_channel_id.id or False})

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
            }


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # @api.onchange('shopify_company_id')
    # def shopify_company_id_onchange(self):
    #     return {'domain': {'shopify_warehouse_id': [('company_id', '=', self.shopify_company_id)]}}

    def _default_instance(self):
        instances = self.env['shopify.instance.ept'].search([])
        return instances and instances[0].id or False

    def _get_default_company(self):
        company_id = self.env.company
        if not company_id:
            raise Warning(_('There is no default company !'))
        return company_id

    # def _domain_company_id(self):
    #     #return True
    #     print(self.shopify_warehouse_id.company_id)
        # domain = "('company_id', '=', self.shopify_warehouse_id.company_id)]"
        # return domain

    shopify_instance_id = fields.Many2one('shopify.instance.ept', 'Instance',
                                          default=_default_instance)

    shopify_company_id = fields.Many2one('res.company', string='Shopify Instance Company',
                                         default=_get_default_company,
                                         help="Orders and Invoices will be generated of this company.")
    shopify_warehouse_id = fields.Many2one('stock.warehouse', string="Warehouse")  # , domain=_domain_company_id)
    shopify_country_id = fields.Many2one('res.country', string="Country")
    shopify_fiscal_position_id = fields.Many2one('account.fiscal.position',
                                                 string='Fiscal Position')
    # is_bom_type_product = fields.Boolean(string="Manage BOM/Kit type products?",
    #                                      help="Manage BOM/Kit type product stock")
    auto_import_product = fields.Boolean(string="Auto Create Product if not found?")
    shopify_sync_product_with = fields.Selection([('sku', 'Internal Reference(SKU)'),
                                                  ('barcode', 'Barcode'),
                                                  ('sku_or_barcode',
                                                   'Internal Reference(SKU) and Barcode'),
                                                  ], string="Sync Product With", default='sku')
    shopify_pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')
    shopify_stock_field = fields.Many2one('ir.model.fields', string='Stock Field')
    # shopify_allow_inconstance_remote_variants = fields.Boolean(
    #     string="Allow Inconstance Remote Variants")
    # payment_term_id = fields.Many2one('account.payment.term', string='Payment Term')
    import_shopify_order_status_ids = fields.Many2many('import.shopify.order.status',
                                                       'shopify_config_settings_order_status_rel',
                                                       'shopify_config_id', 'status_id',
                                                       "Import Order Status",
                                                       help="Select order status in which you want to import the orders from Shopify to Odoo.")
    shopify_section_id = fields.Many2one('crm.team', 'Sales Team')
    shopify_is_use_default_sequence = fields.Boolean("Use Odoo Default Sequence?",
                                                     help="If checked,Then use default sequence of odoo while create sale order.")
    shopify_order_prefix = fields.Char(size=10, string='Order Prefix',
                                       help="Enter your order prefix")
    shopify_discount_product_id = fields.Many2one("product.product", "Discount",
                                                  domain=[('type', '=', 'service')], required=False)
    shopify_apply_tax_in_order = fields.Selection(
        [("odoo_tax", "Odoo Default Tax Behaviour"), ("create_shopify_tax",
                                                      "Create New Tax If Not Found")],
        copy=False, default='create_shopify_tax', help=""" For Shopify Orders :- \n
                    1) Odoo Default Tax Behaviour - The Taxes will be set based on Odoo's
                                 default functional behaviour i.e. based on Odoo's Tax and Fiscal Position configurations. \n
                    2) Create New Tax If Not Found - System will search the tax data received 
                    from Shopify in Odoo, will create a new one if it fails in finding it.""")
    shopify_invoice_tax_account_id = fields.Many2one('account.account', string='Invoice Tax '
                                                                               'Account')
    shopify_credit_tax_account_id = fields.Many2one('account.account', string='Credit Tax Account')
    # shopify_add_discount_tax = fields.Boolean("Calculate Discount Tax", default=False, help="It "
    #                                                                                         "is a mark, it will apply the tax on discount products when importing the orders from Shopify to Odoo.It is not marked, it will not apply the tax on discount.")
    shopify_notify_customer = fields.Boolean("Notify Customer about Update Order Status?",
                                             help="If checked,Notify the customer via email about Update Order Status")
    shopify_auto_closed_order = fields.Boolean("Auto Closed Order", default=False)
    shopify_global_channel_id = fields.Many2one('global.channel.ept', string="Global Channel")

    shopify_user_ids = fields.Many2many('res.users', 'shopify_res_config_settings_res_users_rel',
                                        'res_config_settings_id', 'res_users_id',
                                        string='Responsible User')  # add by bhavesh jadav
    shopify_activity_type_id = fields.Many2one('mail.activity.type',
                                               string="Activity Type")  # add by bhavesh jadav
    shopify_date_deadline = fields.Integer('Deadline Lead Days',
                                           help="its add number of  days in schedule activity deadline date ", default=1)  # add by bhavesh jadav
    is_shopify_create_schedule = fields.Boolean("Create Schedule activity ? ", default=False,
                                             help="If checked, Then Schedule Activity create on order dara queues"
                                                  " will any queue line failed.")  # add by bhavesh jadav
    shopify_sync_product_with_images = fields.Boolean("Shopify Sync/Import Images?",
                                                  help="Check if you want to import images along "
                                                       "with products", default=False)
    create_shopify_products_webhook = fields.Boolean("Manage Products via Webhooks",
                                                help="True : It will create all product related webhooks.\nFalse : All product related webhooks will be deactivated.")
    create_shopify_customers_webhook = fields.Boolean("Manage Customers via Webhooks",
                                                     help="True : It will create all customer related webhooks.\nFalse : All customer related webhooks will be deactivated.")
    create_shopify_orders_webhook = fields.Boolean("Manage Orders via Webhooks",
                                              help="True : It will create all order related webhooks.\nFalse : All "
                                                   "order related webhooks will be deactivated.")
    shopify_default_pos_customer_id = fields.Many2one("res.partner", "Default POS customer",
                                              help="This customer will be set in POS order, when"
                                              "customer is not found.",
                                              domain="[('customer_rank','>', 0)]")
    last_date_order_import = fields.Datetime(string="Last Date Of Order Import",
                                             help="Last date of sync orders from Shopify to Odoo")
    shopify_last_date_customer_import = fields.Datetime(string="Last Date Of Customer Import",
                                                        help="it is used to store last import customer date")
    shopify_last_date_update_stock = fields.Datetime(string="Last Date of Stock Update",
                                                     help="it is used to store last update inventory stock date")
    shopify_last_date_product_import = fields.Datetime(string="Last Date Of Product Import",
                                                       help="it is used to store last import product date")
    shopify_settlement_report_journal_id = fields.Many2one('account.journal',
                                                           string='Payout Report Journal')
    shopify_payout_last_date_import = fields.Date(string="Last Date of Payout Import", help="it is used to store last update shopify payout report")


    @api.onchange('shopify_instance_id')
    def onchange_shopify_instance_id(self):
        instance = self.shopify_instance_id or False
        if instance:
            self.shopify_company_id = instance.shopify_company_id and instance.shopify_company_id.id or False
            self.shopify_warehouse_id = instance.shopify_warehouse_id and instance.shopify_warehouse_id.id or False
            self.shopify_country_id = instance.shopify_country_id and instance.shopify_country_id.id or False
            self.auto_import_product = instance.auto_import_product or False
            # self.is_bom_type_product = instance.is_bom_type_product or False
            self.shopify_sync_product_with = instance.shopify_sync_product_with
            self.shopify_pricelist_id = instance.shopify_pricelist_id and instance.shopify_pricelist_id.id or False
            self.shopify_stock_field = instance.shopify_stock_field and instance.shopify_stock_field.id or False
            # self.shopify_allow_inconstance_remote_variants = instance.shopify_allow_inconstance_remote_variants or False
            # self.payment_term_id = instance.payment_term_id or False
            self.import_shopify_order_status_ids = instance.import_shopify_order_status_ids.ids
            self.shopify_section_id = instance.shopify_section_id.id or False
            self.shopify_order_prefix = instance.shopify_order_prefix
            self.shopify_is_use_default_sequence = instance.is_use_default_sequence
            self.shopify_discount_product_id = instance.discount_product_id and instance.discount_product_id.id or False
            self.shopify_apply_tax_in_order = instance.apply_tax_in_order
            self.shopify_invoice_tax_account_id = instance.invoice_tax_account_id and \
                                                  instance.invoice_tax_account_id.id or False
            self.shopify_credit_tax_account_id = instance.credit_tax_account_id and \
                                                 instance.credit_tax_account_id.id or False
            # self.shopify_add_discount_tax = instance.add_discount_tax
            self.shopify_auto_closed_order = instance.auto_closed_order
            self.shopify_notify_customer = instance.notify_customer
            self.shopify_global_channel_id = instance and instance.shopify_global_channel_id or False
            self.shopify_user_ids = instance.shopify_user_ids or False  # add by bhavesh jadav 28/11/2019
            self.shopify_activity_type_id = instance.shopify_activity_type_id or False  # add by bhavesh jadav 28/11/2019
            self.shopify_date_deadline = instance.shopify_date_deadline or False  # add by bhavesh jadav 28/11/2019
            self.is_shopify_create_schedule = instance.is_shopify_create_schedule or False
            self.shopify_sync_product_with_images = instance.sync_product_with_images or False
            self.create_shopify_products_webhook = instance.create_shopify_products_webhook
            self.create_shopify_customers_webhook = instance.create_shopify_customers_webhook
            self.create_shopify_orders_webhook = instance.create_shopify_orders_webhook

            self.shopify_default_pos_customer_id = instance.shopify_default_pos_customer_id
            self.last_date_order_import = instance.last_date_order_import or False
            self.shopify_last_date_customer_import = instance.shopify_last_date_customer_import or False
            self.shopify_last_date_update_stock = instance.shopify_last_date_update_stock or False
            self.shopify_last_date_product_import = instance.shopify_last_date_product_import or False
            self.shopify_payout_last_date_import = instance.payout_last_import_date or False
            self.shopify_settlement_report_journal_id = instance.shopify_settlement_report_journal_id or False

    def execute(self):
        """This method used to set value in an instance of configuration.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 04/10/2019.
        """
        instance = self.shopify_instance_id
        values = {}
        res = super(ResConfigSettings, self).execute()
        if instance:
#             module_obj = self.env['ir.module.module'].sudo()
#             mrp_module = module_obj.search([('name', '=', 'mrp'), ('state', '=', 'installed')])
            # if not mrp_module and self.is_bom_type_product:
            #     values['is_bom_type_product'] = False
            #     raise Warning(
            #         "MRP module is still not installed in your instance. This feature will only enabled after installing the MRP module.")
            # else:
            #     values['is_bom_type_product'] = self.is_bom_type_product or False
            # values['fiscal_position_id'] = self.shopify_fiscal_position_id and self.shopify_fiscal_position_id.id or False
            # values['pricelist_id'] = self.shopify_pricelist_id and self.shopify_pricelist_id.id or False
            values[
                'shopify_fiscal_position_id'] = self.shopify_fiscal_position_id and self.shopify_fiscal_position_id.id or False
            values[
                'shopify_company_id'] = self.shopify_company_id and self.shopify_company_id.id or False
            values[
                'shopify_warehouse_id'] = self.shopify_warehouse_id and self.shopify_warehouse_id.id or False
            values[
                'shopify_country_id'] = self.shopify_country_id and self.shopify_country_id.id or False
            values['auto_import_product'] = self.auto_import_product or False
            # values['is_bom_type_product'] = self.is_bom_type_product or False
            values['shopify_sync_product_with'] = self.shopify_sync_product_with
            values[
                'shopify_pricelist_id'] = self.shopify_pricelist_id and self.shopify_pricelist_id.id or False
            values[
                'shopify_stock_field'] = self.shopify_stock_field and self.shopify_stock_field.id or False
            # values['payment_term_id'] = self.payment_term_id and self.payment_term_id.id or False
            # values[
            #     'shopify_allow_inconstance_remote_variants'] = self.shopify_allow_inconstance_remote_variants or False
            values['import_shopify_order_status_ids'] = [
                (6, 0, self.import_shopify_order_status_ids.ids)]
            values[
                'shopify_section_id'] = self.shopify_section_id and self.shopify_section_id.id or False
            values[
                'shopify_order_prefix'] = self.shopify_order_prefix
            values[
                'is_use_default_sequence'] = self.shopify_is_use_default_sequence
            values['discount_product_id'] = self.shopify_discount_product_id.id or False
            values['apply_tax_in_order'] = self.shopify_apply_tax_in_order
            values['invoice_tax_account_id'] = self.shopify_invoice_tax_account_id and \
                                               self.shopify_invoice_tax_account_id.id or False
            values['credit_tax_account_id'] = self.shopify_credit_tax_account_id and \
                                              self.shopify_credit_tax_account_id.id or False
            # values['add_discount_tax'] = self.shopify_add_discount_tax
            values['auto_closed_order'] = self.shopify_auto_closed_order
            values['notify_customer'] = self.shopify_notify_customer
            values['shopify_global_channel_id'] = self.shopify_global_channel_id
            values[
                'shopify_activity_type_id'] = self.shopify_activity_type_id and self.shopify_activity_type_id.id or False  # add by bhavesh jadav 28/11/2019
            values['shopify_date_deadline'] = self.shopify_date_deadline or False  # add by bhavesh jadav 28/11/2019
            values.update({'shopify_user_ids': [(6, 0, self.shopify_user_ids.ids)]})  # Add by bhavesh jadav 28/11/2019
            values['is_shopify_create_schedule'] = self.is_shopify_create_schedule  # Add by bhavesh jadav 04/12/2019
            values['sync_product_with_images'] = self.shopify_sync_product_with_images or False  # Add by bhavesh jadav 17/12/2019 for images
            values["create_shopify_products_webhook"] = self.create_shopify_products_webhook
            values["create_shopify_customers_webhook"] = self.create_shopify_customers_webhook
            values["create_shopify_orders_webhook"] = self.create_shopify_orders_webhook
            values["shopify_default_pos_customer_id"] = self.shopify_default_pos_customer_id.id
            values["last_date_order_import"] = self.last_date_order_import
            values["shopify_last_date_customer_import"] = self.shopify_last_date_customer_import
            values["shopify_last_date_update_stock"] = self.shopify_last_date_update_stock
            values["shopify_last_date_product_import"] = self.shopify_last_date_product_import
            values["payout_last_import_date"] = self.shopify_payout_last_date_import or False
            values["shopify_settlement_report_journal_id"] = self.shopify_settlement_report_journal_id or False


            product_webhook_changed = customer_webhook_changed = order_webhook_changed = False
            if instance.create_shopify_products_webhook != self.create_shopify_products_webhook:
                product_webhook_changed = True
            if instance.create_shopify_customers_webhook != self.create_shopify_customers_webhook:
                customer_webhook_changed = True
            if instance.create_shopify_orders_webhook != self.create_shopify_orders_webhook:
                order_webhook_changed = True
            instance.write(values)

            if product_webhook_changed:
                instance.configure_shopify_product_webhook()
            if customer_webhook_changed:
                instance.configure_shopify_customer_webhook()
            if order_webhook_changed:
                instance.configure_shopify_order_webhook()
        return res

    @api.onchange('shopify_company_id')
    def onchange_shopify_company_id(self):
        """
        Code for apply domain on shopify_warehouse_id based on the shopify_company_id.
        @param : self
        @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 18/12/2019.
        """
        # self.shopify_warehouse_id = False
        domain = self.shopify_company_id and [('company_id', '=', self.shopify_company_id.id)] or []
        return {'domain': {'shopify_warehouse_id': domain}}
