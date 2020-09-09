from odoo import models, fields, api, _
from .. import shopify
import logging

_logger = logging.getLogger(__name__)

class ShopifyResPartnerEpt(models.Model):
    _name = "shopify.res.partner.ept"
    _description = 'Shopify Res Partner Ept'

    partner_id = fields.Many2one("res.partner", "partner ID")
    shopify_instance_id = fields.Many2one("shopify.instance.ept", "Instances")
    shopify_customer_id = fields.Char("Shopify Cutstomer Id")

    def find_customer(self, instance, customer):
        """check_partner_contact_address
        :param instance: Object of instance
        :param customer: Response of the customer
        :return: It will return the odoo and Shopify customer object
        """
        shopify_partner = self.search([('shopify_customer_id', '=', customer.get('id')),
                                   ('shopify_instance_id', '=', instance.id)]) if customer.get(
            'id') else False
        if not shopify_partner:
            odoo_partner = self.env['res.partner'].search(
                [('email', '=', customer.get('email')), ('parent_id', '=', False)], limit=1)
        else:
            odoo_partner = shopify_partner.partner_id
        return shopify_partner, odoo_partner

    def process_customers(self, instance, response, partner=False):
        """
        :param instance: Object of instance
        :param customer_queue: Object of customer_queue
        :return: True if successfully process complete
        @author: Angel Patel on Date 09/01/2020.
        """
        if not partner:
            partner_vals = {
                'name': response.get('first_name') + ' ' + response.get('last_name'),
                'email': response.get('email'),
                'customer_rank': 1,
                'is_shopify_customer': True,
                'type': 'invoice',
                'company_type': 'company'
            }
            partner = self.env['res.partner'].create(partner_vals)
        if partner:
            shopify_partner_values = {
                'shopify_customer_id': response.get('id', False),
                'shopify_instance_id': instance.id,
                'partner_id': partner.id
            }
            self.create(shopify_partner_values)
        return True
