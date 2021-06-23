from odoo import models, fields, api, _
from .. import shopify
from odoo.exceptions import Warning
import logging

_logger = logging.getLogger('shopify_webhook_process_start===(Emipro-Webhook):')


class ShopifyWebhookEpt(models.Model):
    _name = "shopify.webhook.ept"
    _description = 'Shopify Webhook'

    state = fields.Selection([('active', 'Active'), ('inactive', 'Inactive')], default='inactive')
    webhook_name = fields.Char(string='Name')
    webhook_action = fields.Selection([('products/create', 'When Product is Create'),
                                       ('products/update', 'When Product is Update'),
                                       ('products/delete', 'When Product is Delete'),
                                       # ('draft_orders/create', 'Draft Orders Create'),
                                       # ('draft_orders/update', 'Draft Orders Update'),
                                       # ('draft_orders/delete', 'Draft Orders Delete'),
                                       ('orders/create', 'When Order is Create'),
                                       # ('orders/paid', 'Orders Paid'),
                                       ('orders/updated', 'When Order is Update'),
                                       # ('orders/fulfilled', 'Orders Fulfilled'),
                                       # ('orders/partially_fulfilled', 'Orders Partially Fulfilled'),
                                       ('orders/cancelled', 'When Order is Cancel'),
                                       ('customers/create', 'When Customer is Create'),
                                       # ('customers/disable', 'Customers Disable'),
                                       # ('customers/enable', 'Customers Enable'),
                                       ('customers/update', 'When Customer is Update'),
                                       # ('customers/delete', 'Customers Delete'),
                                       # ('locations/create', 'Locations Create'),
                                       # ('locations/update', 'Locations Update'),
                                       # ('locations/delete', 'Locations Delete'),
                                       # ('refunds/create', 'refunds Create'),
                                       # ('collection_listings/add', 'collection_listings Create'),
                                       # ('collection_listings/remove', 'collection_listings remove'),
                                       # ('collection_listings/update', 'collection_listings update')
                                       ])
    webhook_id = fields.Char('Webhook Id in Shopify')
    delivery_url = fields.Text("Delivery URL")
    instance_id = fields.Many2one("shopify.instance.ept", string="Webhook created by this Shopify Instance.",
                                  ondelete="cascade")

    @api.model
    def unlink(self):
        """
        delete record of the webhook while deleting the shopify.webhook.ept model record.
        @author: Angel Patel@Emipro Technologies Pvt. Ltd.
        """
        instance = self.instance_id
        instance.connect_in_shopify()
        shopify_webhook = shopify.Webhook()
        for record in self:
            if record.webhook_id:
                try:
                    webhook = shopify_webhook.find(record.webhook_id)
                    webhook.destroy()
                    _logger.info("Delete %s webhook event" % record.webhook_action)
                except:
                    raise Warning("Something went wrong while deleting the webhook.")
        unlink_main = super(ShopifyWebhookEpt, self).unlink()
        self.deactivate_auto_create_webhook(instance)
        return unlink_main

    def deactivate_auto_create_webhook(self, instance):
        _logger.info("deactivate_auto_create_webhook process start")
        product_webhook = instance.list_of_topic_for_webhook('product')
        customer_webhook = instance.list_of_topic_for_webhook('customer')
        order_webhook = instance.list_of_topic_for_webhook('order')
        all_webhook_action = self.search([('instance_id', '=', instance.id)]).mapped('webhook_action')
        if instance.create_shopify_products_webhook:
            result = any(elem in product_webhook for elem in all_webhook_action)
            if not result:
                instance.write({'create_shopify_products_webhook': False})
                _logger.info("Inacive create_shopify_products_webhook from the %s instance" % instance.name)
        if instance.create_shopify_customers_webhook:
            result = any(elem in customer_webhook for elem in all_webhook_action)
            if not result:
                instance.write({'create_shopify_customers_webhook': False})
                _logger.info("Inacive create_shopify_customers_webhook from the %s instance" % instance.name)
        if instance.create_shopify_orders_webhook:
            result = any(elem in order_webhook for elem in all_webhook_action)
            if not result:
                instance.write({'create_shopify_orders_webhook': False})
                _logger.info("Inacive create_shopify_orders_webhook from the %s instance" % instance.name)

    @api.model
    def create(self, values):
        """
        Create method for shopify.webhook.ept
        @author: Angel Patel@Emipro Technologies Pvt. Ltd.
        """
        available_webhook = self.search(
            [('instance_id', '=', values.get('instance_id')), ('webhook_action', '=', values.get('webhook_action'))],
            limit=1)
        if available_webhook:
            raise Warning(_('Webhook is already created with the same action.'))

        result = super(ShopifyWebhookEpt, self).create(values)
        # self._cr.commit()
        result.get_webhook()
        return result

    def get_route(self):
        """
        Gives delivery URL for the webhook as per the Webhook Action.
        @author: Haresh Mori on Date 9-Jan-2020.
        """
        webhook_action = self.webhook_action
        if webhook_action == 'products/create':
            route = "/shopify_odoo_webhook_for_product"
        elif webhook_action == 'products/update':
            route = "/shopify_odoo_webhook_for_product_update"
        elif webhook_action == 'products/delete':
            route = "/shopify_odoo_webhook_for_product_delete"
        # elif webhook_action == 'draft_orders/create':
        #     route = "/shopify_odoo_webhook_for_draft_orders_create"
        # elif webhook_action == 'draft_orders/update':
        #     route = "/shopify_odoo_webhook_for_draft_orders_update"
        # elif webhook_action == 'draft_orders/delete':
        #     route = "/shopify_odoo_webhook_for_draft_orders_delete"
        if webhook_action == 'orders/create':
            route = "/shopify_odoo_webhook_for_order_create"
        # elif webhook_action == 'orders/paid':
        #     route = "/shopify_odoo_webhook_for_orders_paid"
        elif webhook_action == 'orders/updated':
            route = "/shopify_odoo_webhook_for_orders_partially_updated"
        # elif webhook_action == 'orders/fulfilled':
        #     route = "/shopify_odoo_webhook_for_orders_fulfilled"
        # elif webhook_action == 'orders/partially_fulfilled':
        #     route = "/shopify_odoo_webhook_for_orders_partially_fulfilled"
        elif webhook_action == 'orders/cancelled':
            route = "/shopify_odoo_webhook_for_orders_partially_cancelled"
        elif webhook_action == 'customers/create':
            route = "/shopify_odoo_webhook_for_customer_create"
        # elif webhook_action == 'customers/disable':
        #     route = "/shopify_odoo_webhook_for_customer_disable"
        # elif webhook_action == 'customers/enable':
        #     route = "/shopify_odoo_webhook_for_customer_enable"
        elif webhook_action == 'customers/update':
            route = "/shopify_odoo_webhook_for_customer_update"
        # elif webhook_action == 'customers/delete':
        #     route = "/shopify_odoo_webhook_for_customer_delete"
        # elif webhook_action == 'locations/create':
        #     route = "/shopify_odoo_webhook_for_locations_create"
        # elif webhook_action == 'locations/update':
        #     route = "/shopify_odoo_webhook_for_locations_update"
        # elif webhook_action == 'locations/delete':
        #     route = "/shopify_odoo_webhook_for_locations_delete"
        # elif webhook_action == 'refunds/create':
        #     route = "/shopify_odoo_webhook_for_refunds_create"
        # elif webhook_action == 'collection_listings/add':
        #     route = "/shopify_odoo_webhook_for_collection_listings_create"
        # elif webhook_action == 'collection_listings/remove':
        #     route = "/shopify_odoo_webhook_for_collection_listings_remvoe"
        # elif webhook_action == 'collection_listings/update':
        #     route = "/shopify_odoo_webhook_for_collection_listings_update"
        return route

    def get_webhook(self):
        """
        Creates webhook in Shopify Store for webhook in Odoo if no webhook is
        there, otherwise updates status of the webhook, if it exists in Shopify store.
        @author: Haresh Mori on Date 9-Jan-2020.
        """
        instance = self.instance_id
        instance.connect_in_shopify()
        route = self.get_route()
        current_url = instance.get_base_url()
        shopify_webhook = shopify.Webhook()
        #### forcefully set the https in the URL (remove the code while make it live)
        # url = current_url.replace("http", "https") + route
        url = current_url + route
        if url[:url.find(":")] == 'http':
            raise Warning("Address protocol http:// is not supported while creating the webhook")

        responses = shopify_webhook.find()
        if responses:
            for response in responses:
                if response.topic == self.webhook_action:
                    self.write({"webhook_id": response.id, 'delivery_url': response.address,
                                'state': 'active'})
                    return True

        webhook_vals = {"topic": self.webhook_action, "address": url, "format": "json"}
        response = shopify_webhook.create(webhook_vals)
        if response.id:
            new_webhook = response.to_dict()
            self.write({"webhook_id": new_webhook.get("id"), 'delivery_url': url, 'state': 'active'})
            return True
