import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger('shopify_webhook_process_start===(Emipro-Webhook):')


class Main(http.Controller):

    @http.route('/shopify_odoo_webhook_for_customer_create', csrf=False, method="POST",
                auth="public", type="json")
    def shopify_odoo_webhook_for_customer_create(self):
        res, instance, webhook = self.get_basic_info("shopify_odoo_webhook_for_customer_create")
        if res and instance.active and webhook.state == "active":
            _logger.info("process start : shopify odoo webhook for customer create")
            if not res.get('addresses'):
                res_partner_ept = request.env['shopify.res.partner.ept'].sudo()
                shopify_partner, odoo_partner = res_partner_ept.find_customer(
                        instance, res)
                res_partner_ept.process_customers(instance, res, odoo_partner)
            else:
                process_import_export_model = request.env["shopify.process.import.export"].sudo()
                process_import_export_model.webhook_customer_create_process(res, instance)
            request._cr.commit()
        else:
            _logger.info(
                    "%s instance is Archived or 'customers/create' webhook event is currently Inactive. So functionality of the webhook is temporarily disable." % instance.name)
        return

    @http.route('/shopify_odoo_webhook_for_customer_update', csrf=False, method="POST",
                auth="public", type="json")
    def shopify_odoo_webhook_for_customer_update(self):
        res, instance, webhook = self.get_basic_info("shopify_odoo_webhook_for_customer_update")
        if res and instance.active and webhook.state == "active":
            _logger.info("process start : shopify odoo webhook for customer update")
            if res.get('addresses'):
                process_import_export_model = request.env["shopify.process.import.export"].sudo()
                process_import_export_model.webhook_customer_create_process(res, instance)
                request._cr.commit()
        else:
            _logger.info(
                    "%s instance is Archived or 'customers/update' webhook event is currently Inactive. So functionality of the webhook is temporarily disable." % instance.name)
        return

    @http.route("/shopify_odoo_webhook_for_order_create", csrf=False, auth="public", type="json")
    def create_order_webhook(self):
        """
        Route for handling the order creation webhook of Shopify.
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 10-Jan-2020..
        """
        res, instance, odoo_webhook = self.get_basic_info(
                route="shopify_odoo_webhook_for_order_create")
        if not instance.active or not odoo_webhook.state == 'active':
            _logger.info(
                "The method is skipped. It appears the instance:{0} is not active or that the "
                "webhook{1} is not active."
                "".format(instance.name, odoo_webhook.webhook_name))
            return
        _logger.info(
                "CREATE ORDER WEBHOOK call for order: {0}".format(res))
        # Below two line add because when fulfillment status is null it means it is a unshipped order
        # in shopify store so we update the value in response of shopify.
        if not res.get("fulfillment_status"):
            res.update({'fulfillment_status':'unshipped'})
        if res.get("fulfillment_status") in instance.import_shopify_order_status_ids.mapped(
                "status"):
            request.env["sale.order"].sudo().process_shopify_order_via_webhook(res, instance)
        return

    @http.route("/shopify_odoo_webhook_for_orders_partially_updated", csrf=False, auth="public",
                type="json")
    def update_order_webhook(self):
        """
        Route for handling the order modification webhook of Shopify.
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 13-Jan-2020..
        """
        res, instance, odoo_webhook = self.get_basic_info(
            route="shopify_odoo_webhook_for_orders_partially_updated")
        # When the webhook is not active then it will skip the process.
        if not instance.active or not odoo_webhook.state == 'active':
            _logger.info(
                "The method is skipped. It appears the instance:{0} is not active or that the "
                "webhook{1} is not active."
                "".format(instance.name, odoo_webhook.webhook_name))
            return
        _logger.info(
                "UPDATE ORDER WEBHOOK call for order: {0}".format(res))

        if request.env["sale.order"].sudo().search_read([("shopify_instance_id", "=", instance.id),
                                                         ("shopify_order_id", "=", res.get("id")),
                                                         ("shopify_order_number", "=",
                                                          res.get("order_number"))],
                                                        ["id"]):
            request.env["sale.order"].sudo().process_shopify_order_via_webhook(res, instance, True)
        elif not res.get("fulfillment_status"):
            res.update({'fulfillment_status':'unshipped'})
            if res.get("fulfillment_status") in instance.import_shopify_order_status_ids.mapped(
                    "status"):
                request.env["sale.order"].sudo().process_shopify_order_via_webhook(res, instance)
        return

    @http.route("/shopify_odoo_webhook_for_orders_partially_cancelled", csrf=False, auth="public",
                type="json")
    def cancel_order_webhook(self):
        """
        Route for handling the order cancel webhook of Shopify.
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 13-Jan-2020..
        """
        res, instance, odoo_webhook = self.get_basic_info(
            route="shopify_odoo_webhook_for_orders_partially_cancelled")
        # When the webhook is not active then it will skip the process.
        if not instance.active or not odoo_webhook.state == 'active':
            _logger.info(
                "The method is skipped. It appears the instance:{0} is not active or that the "
                "webhook{1} is not active."
                "".format(instance.name, odoo_webhook.webhook_name))
            return
        _logger.info(
                "CANCEL ORDER WEBHOOK call for order: {0}".format(res))

        if request.env["sale.order"].sudo().search_read([("shopify_instance_id", "=", instance.id),
                                                         ("shopify_order_id", "=", res.get("id")),
                                                         ("shopify_order_number", "=",
                                                          res.get("order_number"))],
                                                        ["id"]):
            request.env["sale.order"].sudo().process_shopify_order_via_webhook(res, instance, True)
        return

    @http.route("/shopify_odoo_webhook_for_product", csrf=False, auth="public", type="json")
    def create_product_webhook(self):
        """
        Route for handling the product creation webhook of Shopify.
        @author: Dipak Gogiya on Date 10-Jan-2020.
        """
        self.product_webhook_process('shopify_odoo_webhook_for_product')

    @http.route("/shopify_odoo_webhook_for_product_update", csrf=False, auth="public", type="json")
    def update_product_webhook(self):
        """
        Route for handling the product update webhook of Shopify.
        @author: Dipak Gogiya on Date 10-Jan-2020.
        """
        self.product_webhook_process('shopify_odoo_webhook_for_product_update')

    @http.route("/shopify_odoo_webhook_for_product_delete", csrf=False, auth="public", type="json")
    def delete_product_webhook(self):
        """
        Route for handling the product delete webhook for Shopify
        @author: Dipak Gogiya on Date 10-Jan-2020.
        """
        res, instance, webhook = self.get_basic_info("shopify_odoo_webhook_for_product_delete")
        # When the webhook is not active then it will skip the process.
        if not instance.active or not webhook.state == 'active':
            _logger.info(
                    "The method is skipped. It appears the instance:{0} is not active or that the "
                    "webhook {1} is not active."
                    "".format(instance.name, webhook.webhook_name))
            return
        _logger.info("DELETE PRODUCT WEBHOOK call for product: {0}".format(request.jsonrequest))
        shopify_template = request.env["shopify.product.template.ept"].search(
                [("shopify_tmpl_id", "=", res.get('id')),
                 ("shopify_instance_id", "=", instance.id)], limit=1)
        if shopify_template:
            shopify_template.write({'active':False})
        return

    def product_webhook_process(self, route):
        """
        This method used to process the product webhook response.
        @author: Dipak Gogiya on Date 10-Jan-2020.
        """
        res, instance, webhook = self.get_basic_info(route)
        # When the webhook is not active then it will skip the process.
        if not instance.active or not webhook.state == 'active':
            _logger.info(
                    "The method is skipped. It appears the instance:{0} is not active or that the "
                    "webhook {1} is not active."
                    "".format(instance.name, webhook.webhook_name))
            return
        if route == 'shopify_odoo_webhook_for_product':
            _logger.info("CREATE PRODUCT WEBHOOK call for product: {0}".format(
                    request.jsonrequest.get("title")))
        elif route == 'shopify_odoo_webhook_for_product_update':
            _logger.info("UPDATE PRODUCT WEBHOOK call for product: {0}".format(
                    request.jsonrequest.get("title")))

        woo_template = request.env["shopify.product.template.ept"].with_context(
                active_test=False).search([("shopify_tmpl_id", "=", res.get('id')),
                                           ("shopify_instance_id", "=", instance.id)], limit=1)
        if woo_template:
            request.env["shopify.product.data.queue.ept"].sudo().create_product_queue_from_webhook(
                res, instance)

        elif res.get("published_scope") == "web" and res.get("published_at"):
            request.env["shopify.product.data.queue.ept"].sudo().create_product_queue_from_webhook(
                res, instance)

        return

    def get_basic_info(self, route):
        """
        This method is used return basic info. It will return res and instance.
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 10-Jan-2020..
        """
        res = request.jsonrequest
        host = "https://" + request.httprequest.headers.get('X-Shopify-Shop-Domain')
        instance = request.env["shopify.instance.ept"].sudo().with_context(
            active_test=False).search([("shopify_host", 'ilike', host)], limit=1)
#         instance = request.env["shopify.instance.ept"].sudo().with_context(
#             active_test=False).search([]).filtered(lambda x:x.shopify_host == host)

        webhook = request.env['shopify.webhook.ept'].sudo().search(
                [('delivery_url', 'ilike', route), ('instance_id', '=', instance.id)],
                limit=1)
        return res, instance, webhook
