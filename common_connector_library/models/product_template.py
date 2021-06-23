# -*- encoding: utf-8 -*-

from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_brand_id = fields.Many2one('common.product.brand.ept', string="Brand",
                                       help='Select a brand for this product.')
    ept_image_ids = fields.One2many('common.product.image.ept', 'template_id', string='Images')

    @api.model
    def create(self, vals):
        """
        Inherited for adding the main image in common images.
        @author: Maulik Barad on Date 13-Dec-2019.
        """
        res = super(ProductTemplate, self).create(vals)
        if vals.get("image_1920", False) and res:
            self.env["common.product.image.ept"].create({"sequence":0,
                                                         "image":vals.get("image_1920", False),
                                                         "name":vals.get("name", ""),
                                                         "template_id":res.id})
        return res

    def write(self, vals):
        """
        Inherited for adding the main image in common images.
        @author: Maulik Barad on Date 13-Dec-2019.
        """
        res = super(ProductTemplate, self).write(vals)
        if vals.get("image_1920", False) and self:
            for record in self:
                if vals.get("image_1920") != False:
                    self.env["common.product.image.ept"].create({"sequence":0,
                                                                 "image":vals.get("image_1920", False),
                                                                 "name":record.name,
                                                                 "template_id":record.id})
        return res
