from odoo import models, fields, api, _


class stock_picking(models.Model):
    _inherit = "stock.picking"


    updated_in_shopify = fields.Boolean("Updated In Shopify", default=False)
    is_shopify_delivery_order = fields.Boolean("Shopify Delivery Order", store=True)
    shopify_instance_id = fields.Many2one("shopify.instance.ept", "Instance", store=True)
