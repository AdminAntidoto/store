from odoo import models,fields,api,_

class StockInventory(models.Model):
    _inherit = "stock.inventory"

    is_shopify_product_adjustment = fields.Boolean("Shopify Product Adjustment?")