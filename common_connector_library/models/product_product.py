from datetime import datetime
from odoo.exceptions import Warning
from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = "product.product"

    ept_image_ids = fields.One2many('common.product.image.ept', 'product_id', string='Images')
    vendor_ids = fields.One2many('vendor.stock.ept', 'vendor_product_id', string="Vendor")
    is_drop_ship_product = fields.Boolean(string="Is drop ship product", store=False,
                                          compute="_compute_is_drop_ship_product")

    @api.depends('route_ids')
    def _compute_is_drop_ship_product(self):
        """
        This Method relocates is_drop_ship_product field write.
        If dropship rule get this field _compute_is_drop_ship_product write boolean(True)
        and visible Vendor stock notebook page.
        """
        customer_obj = self.env['stock.location'].search([('usage', '=', 'customer')])
        route_ids = self.route_ids | self.categ_id.route_ids
        stock_rule = self.env['stock.rule'].search(
            [('company_id', '=', self.env.company.id), ('action', '=', 'buy'),
             ('location_id', 'in', customer_obj.ids), ('route_id', 'in', route_ids.ids)]).route_id
        if stock_rule:
            self.is_drop_ship_product = True
        else:
            self.is_drop_ship_product = False

    @api.model
    def create(self, vals):
        """
        Inherited for adding the main image in common images.
        @author: Maulik Barad on Date 13-Dec-2019.
        """
        res = super(ProductProduct, self).create(vals)
        if vals.get("image_1920", False) and res:
            self.env["common.product.image.ept"].create({"sequence":0,
                                                         "image":vals.get("image_1920", False),
                                                         "name":vals.get("name", ""),
                                                         "product_id":res.id,
                                                         "template_id":res.product_tmpl_id.id})
        return res

    def write(self, vals):
        """
        Inherited for adding the main image in common images.
        @author: Maulik Barad on Date 13-Dec-2019.
        """
        res = super(ProductProduct, self).write(vals)
        if vals.get("image_1920", False) and self:
            for record in self:
                if vals.get("image_1920") != False:
                    self.env["common.product.image.ept"].create({"sequence":0,
                                                                 "image":vals.get("image_1920", False),
                                                                 "name":record.name,
                                                                 "product_id":record.id,
                                                                 "template_id":record.product_tmpl_id.id})
        return res

    def get_stock_ept(self, product_id, warehouse_id, fix_stock_type=False, fix_stock_value=0,
                      stock_type='virtual_available'):
        product = self.with_context(warehouse=warehouse_id).browse(product_id.id)
        actual_stock = getattr(product, stock_type)
        if actual_stock >= 1.00:
            if fix_stock_type == 'fix':
                if fix_stock_value >= actual_stock:
                    return actual_stock
                else:
                    return fix_stock_value

            elif fix_stock_type == 'percentage':
                quantity = int((actual_stock * fix_stock_value) / 100.0)
                if quantity >= actual_stock:
                    return actual_stock
                else:
                    return quantity
        return actual_stock

    def get_products_based_on_movement_date(self, from_datetime, company=False):
        """
        This method is give the product list from selected date.
        @author: Krushnasinh Jadeja
        :param from_datetime:from this date it gets the product move list
        :param company:company id
        :return:Product List
        """
        date = str(datetime.strftime(from_datetime, '%Y-%m-%d %H:%M:%S'))
        if company:
            qry = """select product_id from stock_move where date >= '%s' and company_id = %d and
                             state in ('partially_available','assigned','done')""" % (date, company.id)
        else:
            qry = """select product_id from stock_move where date >= '%s' and
                                     state in ('partially_available','assigned','done')""" % date
        self._cr.execute(qry)
        return self._cr.dictfetchall()

    def get_qty_on_hand(self, warehouse, product_list):
        """
        This method is return On hand quantity based on warehouse and product list
        @author:Krushnasinh Jadeja
        :param warehouse: warehouse object
        :param product_list: list of product object
        :return:On hand quantity
        """
        # locations = self.env['stock.location'].search(
        #     [('location_id', 'child_of', warehouse.lot_stock_id.id)])
        locations = self.env['stock.location'].search(
                 [('location_id', 'child_of', warehouse.mapped('lot_stock_id').mapped('id'))])
        location_ids = ','.join(str(e) for e in locations.ids)
        product_list_ids = ','.join(str(e) for e in product_list.ids)
        # Query Updated by Udit
        qry = """select pp.id as product_id,
                COALESCE(sum(sq.quantity)-sum(sq.reserved_quantity),0) as stock
                from product_product pp
                left join stock_quant sq on pp.id = sq.product_id and
                sq.location_id in (%s)
                where pp.id in (%s) group by pp.id;""" % (location_ids, product_list_ids)
        self._cr.execute(qry)
        On_Hand = self._cr.dictfetchall()
        return On_Hand

    def get_forecated_qty(self, warehouse, product_list):
        """
        This method is return forecasted quantity based on warehouse and product list
        @author:Krushnasinh Jadeja
        :param warehouse:warehouse object
        :param product_list:list of product object
        :return: Forecasted Quantity
        """
        # locations = self.env['stock.location'].search(
        #     [('location_id', 'child_of', warehouse.lot_stock_id.id)])
        locations = self.env['stock.location'].search(
            [('location_id', 'child_of', warehouse.mapped('lot_stock_id').mapped('id'))])
        location_ids = ','.join(str(e) for e in locations.ids)
        product_list_ids = ','.join(str(e) for e in product_list.ids)
        # Query Updated by Udit
        qry = """select *
                from (select pp.id as product_id,
                COALESCE(sum(sq.quantity)-sum(sq.reserved_quantity),0) as stock
                from product_product pp
                left join stock_quant sq on pp.id = sq.product_id and
                sq.location_id in (%s)
                where pp.id in (%s) group by pp.id
                union all
                select product_id as product_id,sum(product_qty) as stock from stock_move
                where state in ('assigned') and product_id in (%s) and location_dest_id in (%s)
                group by product_id) as test"""\
              % (location_ids, product_list_ids, product_list_ids, location_ids)
        self._cr.execute(qry)
        Forecasted = self._cr.dictfetchall()
        return Forecasted

    def get_vendor_stock_ept(self):
        """
        This method get the products that routes is Dropship.
        Then it gives the vendor stock of that products.
        :return:Vendor Stock
        """
        customer_obj = self.env['stock.location'].search([('usage', '=', 'customer')])
        stock_routes = self.env['stock.rule'].search(
            [('company_id', '=', self.env.company.id), ('action', '=', 'buy'),
             ('location_id', 'in', customer_obj.ids)]).route_id
        stock_route_ids = stock_routes.ids
        category_obj = \
            self.env['product.category'].search([('route_ids', 'in', stock_route_ids)])
        product_obj = self.env['product.product'].search(
            ['|', ('route_ids', 'in', stock_route_ids), ('categ_id', 'in', category_obj.ids)])
        if product_obj:
            product_list_ids = ','.join(str(e) for e in product_obj.ids)
            qry = """select vendor_product_id as product_id,
                    sum(vendor_stock) as stock from vendor_stock_ept
                    where vendor_product_id in (%s) group by vendor_product_id""" % product_list_ids
            self._cr.execute(qry)
            vendor_stock = self._cr.dictfetchall()
            return vendor_stock

    def get_bom_product_stock_ept(self, product_id, warehouse_id, fix_stock_type=False,
                                  fix_stock_value=0, stock_type='virtual_available'):
        """
        Added by Udit
        This method will check available quantity for componants of BOM type product
        based on the minimum combinations can be made and will give quantity as per the
        fix value or fix stock type passed to it
        :param product_id: BOM type product object.
        :param warehouse_id: Warehouse id.
        :param fix_stock_type: Fix stock type 'fix' or 'percentage'.
        :param fix_stock_value: Fix stock value.
        :param stock_type: stock availability based on field.
        :return: This method will return available quantity for BOM type product.
        """
        module_obj = self.env['ir.module.module'].sudo()
        mrp_module = module_obj.search([('name', '=', 'mrp'), ('state', '=', 'installed')])
        if not mrp_module:
            raise Warning("MRP module must be installed to do this process.")
        actual_stock = product_id.find_bom_product_possible_quantity(warehouse_id, stock_type)
        if actual_stock >= 1.00:
            if fix_stock_type == 'fix':
                if fix_stock_value >= actual_stock:
                    return actual_stock
                else:
                    return fix_stock_value

            elif fix_stock_type == 'percentage':
                quantity = int((actual_stock * fix_stock_value) / 100.0)
                if quantity >= actual_stock:
                    return actual_stock
                else:
                    return quantity
        return actual_stock

    def find_bom_product_possible_quantity(self, warehouse_id, stock_type='virtual_available'):
        """
        Added by Udit
        This method will check available quantity for components of BOM type product
        based on the minimum combinations can be made.
        :param warehouse_id: Warehouse id.
        :param stock_type: stock availability based on field.
        :return: This method will return available quantity for BOM type product.
        """
        bom_lines = self.env['stock.picking'].get_set_product(product=self)
        flag = True
        combination = 0
        for record in bom_lines:
            if record[0].product_id.type != 'product':
                continue
            bom_product_qty = record[1] and record[1].get('qty', 0)
            product = self.with_context(warehouse=warehouse_id).browse(record[0].product_id.id)
            actual_stock = getattr(product, stock_type)
            possible_combination = int(actual_stock / bom_product_qty) \
                if actual_stock > 0 and bom_product_qty > 0 else 0
            if flag:
                combination = possible_combination
                flag = False
            if possible_combination < combination:
                combination = possible_combination
        return combination
