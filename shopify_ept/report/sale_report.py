# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import tools
from odoo import fields, models, api


class sale_report(models.Model):
    _name = "shopify.sale.report"
    _description = "Sales Orders Statistics"
    _auto = False
    _rec_name = 'date'
    _order = 'date desc'

    date = fields.Datetime('Date Order', readonly=True)
    product_id = fields.Many2one('product.product', 'Product', readonly=True)
    product_uom = fields.Many2one('uom.uom', 'Unit of Measure', readonly=True)
    product_uom_qty = fields.Float('# of Qty', readonly=True)
    qty_delivered = fields.Float('Qty Delivered', readonly=True)
    qty_to_invoice = fields.Float('Qty To Invoice', readonly=True)
    qty_invoiced = fields.Float('Qty Invoiced', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Partner', readonly=True)
    company_id = fields.Many2one('res.company', 'Company', readonly=True)
    user_id = fields.Many2one('res.users', 'Salesperson', readonly=True)
    price_total = fields.Float('Total Price', readonly=True)
    price_subtotal = fields.Float('Untaxed Total Price', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', 'Product Template', readonly=True)
    categ_id = fields.Many2one('product.category', 'Product Category', readonly=True)
    nbr = fields.Integer('# of Lines', readonly=True)
    pricelist_id = fields.Many2one('product.pricelist', 'Pricelist', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', 'Analytic Account', readonly=True)
    team_id = fields.Many2one('crm.team', 'Sales Team', readonly=True)
    country_id = fields.Many2one('res.country', 'Partner Country', readonly=True)
    commercial_partner_id = fields.Many2one('res.partner', 'Commercial Entity', readonly=True)
    shopify_instance_id = fields.Many2one("shopify.instance.ept", "Instance", readonly=True)
    state = fields.Selection([
        ('draft', 'Draft Quotation'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sales Order'),
        ('done', 'Sales Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True)

    def _select(self):
        select_str = """
            WITH currency_rate (currency_id, rate, date_start, date_end) AS (
                    SELECT r.currency_id, r.rate, r.name AS date_start,
                        (SELECT name FROM res_currency_rate r2
                        WHERE r2.name > r.name AND
                            r2.currency_id = r.currency_id
                         ORDER BY r2.name ASC
                         LIMIT 1) AS date_end
                    FROM res_currency_rate r
                )
             SELECT min(l.id) as id,
                    l.product_id as product_id,
                    t.uom_id as product_uom,
                    sum(l.product_uom_qty / u.factor * u2.factor) as product_uom_qty,
                    sum(l.qty_delivered / u.factor * u2.factor) as qty_delivered,
                    sum(l.qty_invoiced / u.factor * u2.factor) as qty_invoiced,
                    sum(l.qty_to_invoice / u.factor * u2.factor) as qty_to_invoice,
                    sum(l.price_total * COALESCE(cr.rate, 1.0)) as price_total,
                    sum(l.price_subtotal * COALESCE(cr.rate, 1.0)) as price_subtotal,
                    count(*) as nbr,
                    s.date_order as date,
                    s.state as state,
                    s.partner_id as partner_id,
                    s.user_id as user_id,
                    s.company_id as company_id,
                    extract(epoch from avg(date_trunc('day',s.date_order)-date_trunc('day',s.create_date)))/(24*60*60)::decimal(16,2) as delay,
                    t.categ_id as categ_id,
                    s.pricelist_id as pricelist_id,
                    s.analytic_account_id as analytic_account_id,
                    s.team_id as team_id,
                    p.product_tmpl_id,
                    partner.country_id as country_id,
                    partner.commercial_partner_id as commercial_partner_id,
                    aie.id as shopify_instance_id
        """
        return select_str

    def _from(self):
        from_str = """
                sale_order_line l
                      join sale_order s on (l.order_id=s.id)
                      join res_partner partner on s.partner_id = partner.id
                      join shopify_instance_ept aie on aie.id = s.shopify_instance_id
                        left join product_product p on (l.product_id=p.id)
                            left join product_template t on (p.product_tmpl_id=t.id)
                    left join uom_uom u on (u.id=l.product_uom)
                    left join uom_uom u2 on (u2.id=t.uom_id)
                    left join product_pricelist pp on (s.pricelist_id = pp.id)
                    left join currency_rate cr on (cr.currency_id = pp.currency_id and
                        cr.date_start <= coalesce(s.date_order, now()) and
                        (cr.date_end is null or cr.date_end > coalesce(s.date_order, now())))
        """
        return from_str

    def _group_by(self):
        group_by_str = """
            GROUP BY l.product_id,
                    l.order_id,
                    t.uom_id,
                    t.categ_id,
                    s.date_order,
                    s.partner_id,
                    s.user_id,
                    s.state,
                    s.company_id,
                    s.pricelist_id,
                    s.analytic_account_id,
                    s.team_id,
                    p.product_tmpl_id,
                    partner.country_id,
                    partner.commercial_partner_id,
                    aie.id
        """
        return group_by_str

    def init(self):
        # self._table = sale_report
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (    
            %s
            FROM ( %s )
            %s
            )""" % (self._table, self._select(), self._from(), self._group_by()))
