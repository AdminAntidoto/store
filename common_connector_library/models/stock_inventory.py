import time
from odoo import models, api


class StockInventory(models.Model):
    _inherit = "stock.inventory"

    """
    products = [{'product_id':product_obj,'product_qty':qty,'location_id':location_id},
    {'product_id':product_obj,'product_qty':qty,'location_id':location_id}]
    """

    @api.model
    def create_stock_inventory(self, products, location_id, auto_validate=False):
        """
        Added by Udit
        This method will create inventory based on products and location passed to this method.
        :param products: List of dictionary as mentioned above the method.
        :param location_id: Location for which need an inventory adjustment.
        :param auto_validate: If also need to validate inventory then pass "True"
                              otherwise "False".
        """
        if products:
            inventory_name = 'product_inventory_%s' % (time.strftime("%Y-%m-%d %H:%M:%S"))
            inventory_products = [p['product_id'].id for p in list(products)]
            inventory_vals = {
                'name': inventory_name,
                'location_ids': [(6, 0, [location_id.id])] if location_id else False,
                'date': time.strftime("%Y-%m-%d %H:%M:%S"),
                'product_ids': [(6, 0, inventory_products)],
                'prefill_counted_quantity': 'zero',
                "company_id":location_id.company_id.id if location_id else self.env.company.id
            }
            inventory = self.create(inventory_vals)
            inventory.create_inventory_lines(products, location_id)
            inventory.action_start()
            if auto_validate:
                inventory.action_validate()

            return inventory
        return False

    @api.model
    def create_inventory_lines(self, products, location_id):
        """
        Added by Udit
        This method will create inventory as per the data passed to the method.
        :param products: List of dictionary for which requested to make inventory adjustment.
        :param location_id: Location for which need an inventory adjustment.
        """
        inventory_line_obj = self.env['stock.inventory.line']
        vals_list = []
        for product_data in products:
            if product_data.get('product_id', False) and product_data.get('product_qty', False):
                val = self.prepare_inventory_line_vals(product_data.get('product_id'),
                                                       product_data.get('product_qty'),
                                                       location_id)
                vals_list.append(val)
        for record in vals_list:
            inventory_line_obj.create(record)
        return True

    def prepare_inventory_line_vals(self, product, qty, location):
        """
        Added by Udit
        This method will create inventory line vals.
        :param product: Product object for which we need to create inventory adjustment.
        :param qty: Actual quantity.
        :param location: Location for which need an inventory adjustment.
        :return: This method will return inventory line vals.
        """
        product_obj = self.env['product.product']
        vals = {
            'company_id': self.company_id.id,
            'product_id': product.id,
            'inventory_id': self.id,
            'theoretical_qty': product_obj.get_theoretical_quantity(product.id, location.id),
            'location_id': location.id,
            'product_qty': 0 if qty <= 0 else qty,
            'product_uom_id': product.uom_id.id if product.uom_id else False,
        }
        return vals
