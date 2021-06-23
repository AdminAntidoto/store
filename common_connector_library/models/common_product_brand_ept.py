# -*- encoding: utf-8 -*-

from odoo import models, fields


class CommonProductBrandEpt(models.Model):
    _name = 'common.product.brand.ept'
    _description = 'common.product.brand.ept'

    name = fields.Char('Brand Name', required="True")
    description = fields.Text('Description', translate=True)
    partner_id = fields.Many2one('res.partner', string='Partner',
                                 help='Select a partner for this brand if it exists.',
                                 ondelete='restrict')
    logo = fields.Binary('Logo File')
