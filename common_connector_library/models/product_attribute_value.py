from odoo import models


class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"

    def get_attribute_values(self, name, attribute_id, auto_create=False):
        """

        :param name: name of attribute value
        :param attribute_id:id of attribute
        :param auto_create: True or False
        :return: attribute values
        """
        attribute_values = self.search(
            [('name', '=ilike', name), ('attribute_id', '=', attribute_id)])
        if not attribute_values:
            if auto_create:
                return self.create(({'name': name, 'attribute_id': attribute_id}))
            else:
                return False
        else:
            return attribute_values
