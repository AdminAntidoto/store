from odoo import models, fields, api, _


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    # This field use to identify the Shopify delivery method
    shopify_code = fields.Char("Shopify Delivery Code")
    shopify_source = fields.Char("Shopify Delivery Source")

    # This method is old flow of delivery method process
    # def shopify_search_create_delivery_carrier(self, line):
    #     delivery_method = line.get('source')
    #     delivery_title = line.get('title')
    #     carrier = False
    #     if delivery_method:
    #         carrier = self.search(
    #                 [('shopify_code', '=', delivery_method)], limit=1)
    #         if not carrier:
    #             carrier = self.search(
    #                     ['|', ('name', '=', delivery_title),
    #                      ('shopify_code', '=', delivery_method)], limit=1)
    #         if not carrier:
    #             carrier = self.search(
    #                     ['|', ('name', 'ilike', delivery_title),
    #                      ('shopify_code', 'ilike', delivery_method)], limit=1)
    #         if not carrier:
    #             product_template = self.env['product.template'].search(
    #                     [('name', '=', delivery_title), ('type', '=', 'service')], limit=1)
    #             if not product_template:
    #                 product_template = self.env['product.template'].create(
    #                         {'name':delivery_title, 'type':'service'})
    #             carrier = self.create(
    #                     {'name':delivery_title, 'shopify_code':delivery_method,
    #                      'product_id':product_template.product_variant_ids[0].id})
    #     return carrier

    def shopify_search_create_delivery_carrier(self, line):
        delivery_source = line.get('source')
        delivery_code = line.get('code')
        delivery_title = line.get('title')
        carrier = False
        if delivery_source and delivery_code:
            carrier = self.search(
                [('shopify_source', '=', delivery_source), ('shopify_code', '=', delivery_code)], limit=1)
            if not carrier:
                carrier = self.search(
                    [('name', '=', delivery_title)], limit=1)
                if carrier:
                    carrier.write({'shopify_source':delivery_source,'shopify_code':delivery_code})
            if not carrier:
                product_template = self.env['product.template'].search(
                    [('name', '=', delivery_title), ('type', '=', 'service')], limit=1)
                if not product_template:
                    product_template = self.env['product.template'].create(
                        {'name': delivery_title, 'type': 'service'})
                carrier = self.create(
                    {'name': delivery_title, 'shopify_code': delivery_code, 'shopify_source': delivery_source,
                     'product_id': product_template.product_variant_ids[0].id})
        return carrier
