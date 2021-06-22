from odoo import fields, models

"""This class is used to set global channel relation in related
    Sale order, Pickings, Moves, Account move, Account move line
    @author: Dimpal
    @added on: 5/oct/2019
"""


class GlobalChannel(models.Model):
    _name = 'global.channel.ept'
    _description = 'Global Channel'

    name = fields.Char('Global Channel')
