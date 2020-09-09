from odoo import models


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    def get_attribute(self, attribute_string, type='radio', create_variant='always',
                      auto_create=False):
        """

        :param attribute_string: name of attribute
        :param type: type of attribute
        :param create_variant: when variant create
        :param auto_create: True or False
        :return: attributes
        """
        attributes = self.search(
            [('name', '=ilike', attribute_string), ('create_variant', '=', create_variant)])
        if not attributes and auto_create:
                return self.create(({'name': attribute_string, 'create_variant': create_variant,
                                     'display_type': type}))
        return attributes
