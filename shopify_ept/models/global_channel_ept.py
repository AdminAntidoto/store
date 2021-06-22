from odoo import fields, models

class GlobalChannelEpt(models.Model):
    _inherit = 'global.channel.ept'

    shopify_instance_id = fields.Many2one("shopify.instance.ept", "Instances")
