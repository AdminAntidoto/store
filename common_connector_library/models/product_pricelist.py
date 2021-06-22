from odoo import models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    def get_product_price_ept(self, product, partner=False):
        """

        :param product: product id
        :param pricelist_id: pricelist id
        :param partner: partner id or False
        :return: price
        """
        price = self.get_product_price(product, 1.0, partner=partner,
                                            uom_id=product.uom_id.id)
        return price

    def set_product_price_ept(self, product_id, price, min_qty=1):
        """

        :param product_id: Product id
        :param pricelist_id: Pricelist id
        :param price: Price
        :param min_qty: qty
        :return: product_pricelist_item
        """
        product_pricelist_item_obj = self.env['product.pricelist.item']
        domain = []
        domain.append(('pricelist_id', '=', self.id))
        domain.append(('product_id', '=', product_id))
        domain.append(('min_quantity', '=', min_qty))
        product_pricelist_item = product_pricelist_item_obj.search(domain)
        if product_pricelist_item:
            product_pricelist_item.write({'fixed_price': price})
        else:
            vals = {
                'pricelist_id': self.id,
                'applied_on': '0_product_variant',
                'product_id': product_id,
                'min_quantity': min_qty,
                'fixed_price': price,
            }
            new_record = product_pricelist_item_obj.new(vals)
            new_record._onchange_product_id()
            new_vals = product_pricelist_item_obj._convert_to_write(
                    {name:new_record[name] for name in new_record._cache})
            product_pricelist_item = product_pricelist_item_obj.create(new_vals)
        return product_pricelist_item
