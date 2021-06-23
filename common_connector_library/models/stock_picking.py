from odoo.tools import float_round
from odoo.tools.float_utils import float_compare

from odoo import fields, models, _


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # Added By Dimpal on 5/oct/2019
    global_channel_id = fields.Many2one('global.channel.ept', string='Global Channel')

    def get_set_product(self, product):
        try:
            bom_obj = self.env['mrp.bom']
            bom_point = bom_obj.sudo()._bom_find(product=product)
            from_uom = product.uom_id
            to_uom = bom_point.product_uom_id
            factor = from_uom._compute_quantity(1, to_uom) / bom_point.product_qty
            bom, lines = bom_point.explode(product, factor, picking_type=bom_point.picking_type_id)
            return lines
        except:
            return {}

    def _put_in_pack_ept(self, operation, package):
        operation_ids = self.env['stock.move.line']
        if float_compare(operation.qty_done, operation.product_uom_qty,
                         precision_rounding=operation.product_uom_id.rounding) >= 0:
            operation_ids |= operation
        else:
            quantity_left_todo = float_round(
                operation.product_uom_qty - operation.qty_done,
                precision_rounding=operation.product_uom_id.rounding,
                rounding_method='UP')
            new_operation = operation.copy(
                default={'product_uom_qty': 0, 'qty_done': operation.qty_done})
            operation.write({'product_uom_qty': quantity_left_todo, 'qty_done': 0.0})
            new_operation.write({'product_uom_qty': operation.qty_done})
            operation_ids |= new_operation
        package and operation_ids.write({'result_package_id': package.id})
        return True

    """ Use Below Method For Multipler Traking Number Pass Parameter
    picking_id = For Ex:- 24
    datas = {'product_id':{'product_qty':qty,'traking_no':traking_no},
            'product_id':{'product_qty':qty,'traking_no':traking_no}} 
    datas = {'10':{'product_qty':1,'traking_no':784512369547},
            '12':{'product_qty':2,'traking_no':784512369548}}
    allow_extra_move if no one moves find related picking 
    and product which you have pass in parameter..
    forcefully create the moves if allow_extra_move=True
    """

    def process_delivery_order(self, picking_id, datas, allow_extra_move=False):
        move_obj = self.env['stock.move']
        quant_package_obj = self.env["stock.quant.package"]
        stock_move_line_obj = self.env['stock.move.line']
        pick_ids = []
        picking_obj = self.browse(picking_id)
        for key, vals in list(datas.items()):
            product_id = key
            qty = vals.get('product_qty', '')
            traking_no = vals.get('traking_no', '')
            package = False
            package = quant_package_obj.search([('tracking_no', '=', traking_no)])
            if not package:
                package = quant_package_obj.create({'tracking_no': traking_no})
            product = self.env['product.product'].browse(product_id)
            """ Find out the Moves Lines Related to Picking Id and Product Id. """
            move_lines = move_obj.search([('picking_id', '=', picking_id),
                                          ('product_id', '=', product_id),
                                          ('state', 'in',
                                           ('confirmed', 'assigned', 'partially_available'))])
            is_kit_product = False
            """ If No Moves Lines Find out the Moves Lines Related to Picking Id
                and Product Id set in the sale order line.
                If move_lines that move_lines consider as kit_product moves.. """
            if not move_lines:
                move_lines = move_obj.search([('picking_id', '=', picking_id),
                                              ('sale_line_id.product_id', '=', product_id),
                                              ('state', 'in',
                                               ('confirmed', 'assigned', 'partially_available'))])
                is_kit_product = True
            """ If No one moves find..Forcefully create the moves if allow extra move=True """
            if not move_lines:
                if allow_extra_move == True:
                    move = move_obj.create({
                        'product_id': product_id,
                        'product_uom_qty': float(qty) or 0,
                        'picking_id': picking_id,
                        'name': product.name,
                        'location_id': picking_obj.location_id.id,
                        'location_dest_id': picking_obj.location_dest_id.id,
                    })
                    move._action_confirm()
                    move._action_assign()
            """ If moves_lines and not Kit Product check the qty if qty less than zero break
            the tranc.. if qty not less than zero calculate remaning qty of move line
            and find out the operation which is done qty less than or equal to zero.
            done qty of operation..then put the picking in to package. """
            if not is_kit_product:
                qty_left = qty
                for move in move_lines:
                    if float(qty_left) <= 0.0:
                        break
                    move_line_remaning_qty = (move.product_uom_qty) - (
                        sum(move.move_line_ids.mapped('qty_done')))
                    operations = move.move_line_ids.filtered(
                        lambda o: o.qty_done <= 0 and not o.result_package_id)
                    for operation in operations:
                        if operation.product_uom_qty <= float(qty_left):
                            op_qty = operation.product_uom_qty
                        else:
                            op_qty = qty_left
                        operation.write({'qty_done': op_qty})
                        self._put_in_pack_ept(operation, package)
                        qty_left = float_round(float(qty_left) - op_qty,
                                               precision_rounding=operation.product_uom_id.rounding,
                                               rounding_method='UP')
                        move_line_remaning_qty = move_line_remaning_qty - op_qty
                        if qty_left <= 0.0:
                            break
                    if float(qty_left) > 0.0 and move_line_remaning_qty > 0.0:
                        if move_line_remaning_qty <= float(qty_left):
                            op_qty = move_line_remaning_qty
                        else:
                            op_qty = qty_left
                        stock_move_line_obj.create({
                            'product_id': move.product_id.id,
                            'product_uom_id': move.product_id.uom_id.id,
                            'picking_id': picking_id,
                            'qty_done': float(op_qty) or 0,
                            'result_package_id': package and package.id or False,
                            'location_id': picking_obj.location_id.id,
                            'location_dest_id': picking_obj.location_dest_id.id,
                            'move_id': move.id
                        })
                        qty_left = float_round(qty_left - op_qty,
                                               precision_rounding=move.product_id.uom_id.rounding,
                                               rounding_method='UP')
                        if float(qty_left) <= 0.0:
                            break
                if float(qty_left) > 0.0:
                    stock_move_line_obj.create({
                        'product_id': move_lines[0].product_id.id,
                        'product_uom_id': move_lines[0].product_id.uom_id.id,
                        'picking_id': picking_id,
                        'qty_done': float(qty_left) or 0,
                        'result_package_id': package and package.id or False,
                        'location_id': picking_obj.location_id.id,
                        'location_dest_id': picking_obj.location_dest_id.id,
                        'move_id': move_lines[0].id,
                    })
                pick_ids.append(picking_id)
            else:
                one_set_product_dict = self.get_set_product(move_lines and move_lines[0], product)
                if not one_set_product_dict:
                    continue
                transfer_product_qty = {}
                for bom_line, line_data in one_set_product_dict:
                    qty = line_data['qty']
                    product_id = bom_line.product_id.id
                    transfer_product_qty.update({product_id: qty})
                for product_id, bom_qty in transfer_product_qty.items():
                    file_qty = qty
                    if bom_qty <= 0.0:
                        continue
                    if transfer_product_qty.get(product_id) <= 0.0:
                        continue
                    qty_left = file_qty * bom_qty
                    product_move_lines = move_lines.filtered(
                        lambda move_line: move_line.product_id.id == product_id)
                    for product_move_line in product_move_lines:
                        operations = product_move_line.move_line_ids.filtered(
                            lambda o: o.qty_done <= 0 and not o.result_package_id)
                        move_line_remaning_qty = (product_move_line.product_uom_qty) - (
                            sum(product_move_line.move_line_ids.mapped('qty_done')))
                        for operation in operations:
                            if operation.product_uom_qty <= qty_left:
                                op_qty = operation.product_uom_qty
                            else:
                                op_qty = qty_left
                            operation.write({'qty_done': op_qty})
                            self._put_in_pack_ept(operation, package)
                            qty_left = \
                                float_round(qty_left - op_qty,
                                            precision_rounding=operation.product_uom_id.rounding,
                                            rounding_method='UP')
                            move_line_remaning_qty = move_line_remaning_qty - op_qty
                            if float(qty_left) <= 0.0:
                                transfer_product_qty.update({product_id: 0.0})
                                break
                        if float(qty_left) > 0.0 and move_line_remaning_qty > 0.0:
                            if move_line_remaning_qty <= float(qty_left):
                                op_qty = move_line_remaning_qty
                            else:
                                op_qty = qty_left
                            stock_move_line_obj.create({
                                'product_id': product_move_line.product_id.id,
                                'product_uom_id': product_move_line.product_id.uom_id.id,
                                'picking_id': picking_id,
                                'qty_done': float(op_qty) or 0,
                                'result_package_id': package and package.id or False,
                                'location_id': picking_obj.location_id.id,
                                'location_dest_id': picking_obj.location_dest_id.id,
                                'move_id': product_move_line.id,
                            })
                            qty_left = float_round(qty_left - op_qty,
                                                   precision_rounding=
                                                   product_move_line.product_id.uom_id.rounding,
                                                   rounding_method='UP')
                            if float(qty_left) <= 0.0:
                                transfer_product_qty.update({product_id: 0.0})
                                break
                    if float(qty_left) > 0.0 and float(op_qty):
                        stock_move_line_obj.create(
                            {
                                'product_id': product_move_lines and product_move_lines[
                                    0].product_id.id,
                                'product_uom_id': product_move_lines and product_move_lines[
                                    0].product_id.uom_id.id,
                                'picking_id': picking_id,
                                'qty_done': float(qty_left) or 0,
                                'result_package_id': package and package.id or False,
                                'location_id': picking_obj.location_id.id,
                                'location_dest_id': picking_obj.location_dest_id.id,
                                'move_id': product_move_lines and product_move_lines[0].id,
                            })
                pick_ids.append(picking_id)
        if pick_ids:
            pickings = self.search([('state', '=', 'assigned'), ('id', 'in', list(set(pick_ids)))])
            pickings and pickings.action_done()
            pickings = self.search([('state', '!=', 'done'), ('id', 'in', list(set(pick_ids)))])
            pickings and pickings.action_done()

    """Use Below Method For single traking_no
    datas = [{'product_id':id,'product_qty':qty},{'product_id':id,'product_qty':qty}]
    picking_id - Stock Picking Id(Require),
    Traking No = If Available(Not require)
    """

    def process_delivery_order_ept(self, picking_id, datas, traking_no=False,
                                   allow_extra_move=False):
        move_obj = self.env['stock.move']
        stock_move_line_obj = self.env['stock.move.line']
        pick_ids = []
        picking_obj = self.browse(picking_id)
        if traking_no:
            picking_obj.write({'carrier_tracking_ref': traking_no})

        for vals in datas:  # list(datas.items())
            product_id = vals.get('product_id', '')
            qty = vals.get('product_qty', '')
            product = self.env['product.product'].browse(product_id)
            """ Find out the Moves Lines Related to Picking Id and Product Id. """
            move_lines = move_obj.search([('picking_id', '=', picking_id),
                                          ('product_id', '=', product_id),
                                          ('state', 'in',
                                           ('confirmed', 'assigned', 'partially_available'))])
            is_kit_product = False
            """ If No Moves Lines Find out the Moves Lines Related to Picking Id and
            Product Id set in the sale order line.
            If move_lines that move_lines consider as kit_product moves.. """
            if not move_lines:
                move_lines = move_obj.search([('picking_id', '=', picking_id),
                                              ('sale_line_id.product_id', '=', product_id),
                                              ('state', 'in',
                                               ('confirmed', 'assigned', 'partially_available'))])
                is_kit_product = True
            """ If No one moves find..Forcefully create the moves if allow extra move=True """
            if not move_lines:
                if allow_extra_move == True:
                    move = move_obj.create({
                        'product_id': product_id,
                        'product_uom_qty': float(qty) or 0,
                        'picking_id': picking_id,
                        'name': product.name,
                        'location_id': picking_obj.location_id.id,
                        'location_dest_id': picking_obj.location_dest_id.id,
                    })
                    move._action_confirm()
                    move._action_assign()
            """ If moves_lines and not Kit Product check the qty if qty less than zero break the
            tranc.. if qty not less than zero calculate remaning qty of move line and find out
            the operation which is done qty less than or equal to zero.done qty of operation..
            then put the picking in to package. """
            if not is_kit_product:
                qty_left = qty
                for move in move_lines:
                    if float(qty_left) <= 0.0:
                        break
                    move_line_remaning_qty = (move.product_uom_qty) - (
                        sum(move.move_line_ids.mapped('qty_done')))
                    operations = move.move_line_ids.filtered(
                        lambda o: o.qty_done <= 0 and not o.result_package_id)
                    for operation in operations:
                        if operation.product_uom_qty <= float(qty_left):
                            op_qty = operation.product_uom_qty
                        else:
                            op_qty = qty_left
                        operation.write({'qty_done': op_qty})
                        self._put_in_pack_ept(operation, False)
                        qty_left = float_round(float(qty_left) - op_qty,
                                               precision_rounding=operation.product_uom_id.rounding,
                                               rounding_method='UP')
                        move_line_remaning_qty = move_line_remaning_qty - op_qty
                        if qty_left <= 0.0:
                            break
                    if float(qty_left) > 0.0 and move_line_remaning_qty > 0.0:
                        if move_line_remaning_qty <= float(qty_left):
                            op_qty = move_line_remaning_qty
                        else:
                            op_qty = qty_left
                        stock_move_line_obj.create({
                            'product_id': move.product_id.id,
                            'product_uom_id': move.product_id.uom_id.id,
                            'picking_id': picking_id,
                            'qty_done': float(op_qty) or 0,
                            'location_id': picking_obj.location_id.id,
                            'location_dest_id': picking_obj.location_dest_id.id,
                            'move_id': move.id
                        })
                        qty_left = float_round(qty_left - op_qty,
                                               precision_rounding=move.product_id.uom_id.rounding,
                                               rounding_method='UP')
                        if float(qty_left) <= 0.0:
                            break
                if float(qty_left) > 0.0:
                    stock_move_line_obj.create({
                        'product_id': move_lines and move_lines[0].product_id.id,
                        'product_uom_id': move_lines and move_lines[0].product_id.uom_id.id,
                        'picking_id': picking_id,
                        'qty_done': float(qty_left) or 0,
                        'location_id': picking_obj.location_id.id,
                        'location_dest_id': picking_obj.location_dest_id.id,
                        'move_id': move_lines and move_lines[0].id,
                    })
                pick_ids.append(picking_id)
            else:
                one_set_product_dict = self.get_set_product(move_lines and move_lines[0], product)
                if not one_set_product_dict:
                    continue
                transfer_product_qty = {}
                for bom_line, line_data in one_set_product_dict:
                    qty = line_data['qty']
                    product_id = bom_line.product_id.id
                    transfer_product_qty.update({product_id: qty})
                for product_id, bom_qty in transfer_product_qty.items():
                    file_qty = qty
                    if bom_qty <= 0.0:
                        continue
                    if transfer_product_qty.get(product_id) <= 0.0:
                        continue
                    qty_left = file_qty * bom_qty
                    product_move_lines = move_lines.filtered(
                        lambda move_line: move_line.product_id.id == product_id)
                    for product_move_line in product_move_lines:
                        operations = product_move_line.move_line_ids.filtered(
                            lambda o: o.qty_done <= 0 and not o.result_package_id)
                        move_line_remaning_qty = (product_move_line.product_uom_qty) - (
                            sum(product_move_line.move_line_ids.mapped('qty_done')))
                        for operation in operations:
                            if operation.product_uom_qty <= qty_left:
                                op_qty = operation.product_uom_qty
                            else:
                                op_qty = qty_left
                            operation.write({'qty_done': op_qty})
                            self._put_in_pack_ept(operation, False)
                            qty_left = float_round(qty_left - op_qty,
                                                   precision_rounding=
                                                   operation.product_uom_id.rounding,
                                                   rounding_method='UP')
                            move_line_remaning_qty = move_line_remaning_qty - op_qty
                            if float(qty_left) <= 0.0:
                                transfer_product_qty.update({product_id: 0.0})
                                break
                        if float(qty_left) > 0.0 and move_line_remaning_qty > 0.0:
                            if move_line_remaning_qty <= float(qty_left):
                                op_qty = move_line_remaning_qty
                            else:
                                op_qty = qty_left
                            stock_move_line_obj.create({
                                'product_id': product_move_line.product_id.id,
                                'product_uom_id': product_move_line.product_id.uom_id.id,
                                'picking_id': picking_id,
                                'qty_done': float(op_qty) or 0,
                                'location_id': picking_obj.location_id.id,
                                'location_dest_id': picking_obj.location_dest_id.id,
                                'move_id': product_move_line.id,
                            })
                            qty_left = float_round(qty_left - op_qty,
                                                   precision_rounding=
                                                   product_move_line.product_id.uom_id.rounding,
                                                   rounding_method='UP')
                            if float(qty_left) <= 0.0:
                                transfer_product_qty.update({product_id: 0.0})
                                break
                    if float(qty_left) > 0.0:
                        stock_move_line_obj.create({
                            'product_id': product_move_lines and product_move_lines[
                                0].product_id.id,
                            'product_uom_id': product_move_lines and product_move_lines[
                                0].product_id.uom_id.id,
                            'picking_id': picking_id,
                            'qty_done': float(qty_left) or 0,
                            'location_id': picking_obj.location_id.id,
                            'location_dest_id': picking_obj.location_dest_id.id,
                            'move_id': product_move_lines and product_move_lines[0].id,
                        })
                pick_ids.append(picking_id)
        if pick_ids:
            pickings = self.search([('state', '=', 'assigned'), ('id', 'in', list(set(pick_ids)))])
            pickings and pickings.action_done()
            pickings = self.search([('state', '!=', 'done'), ('id', 'in', list(set(pick_ids)))])
            pickings and pickings.action_done()

    """ Pass Parameter Datas Dictionary which you have to create Return Picking..
    datas = {'picking_id':id,'move_id':move_id,'location_dest_id':dest_loction,'qty':qty}
    
    picking_id,location_dest_id,datas={'product_id':qty,'product_id':qty,'product_id':qty}
    """

    def create_return_picking_ept(self, datas):
        picking_obj = self.browse(datas.get('picking_id', ''))
        return_picking = picking_obj.copy({
            'move_lines': [],
            'picking_type_id': picking_obj.picking_type_id.id,
            'state': 'draft',
            'origin': _("Return of %s") % picking_obj.name,
            'location_id': picking_obj.location_dest_id.id,
            'location_dest_id': picking_obj.location_id.id
        })
        move = self.env['stock.move'].browse(datas.get('move_id', ''))
        move.copy({
            'product_id': move.product_id.id,
            'product_uom_qty': datas.get('qty') or move.quantity_done,
            'picking_id': return_picking.id,
            'state': 'draft',
            'location_id': move.location_dest_id.id,
            'location_dest_id': datas.get('location_dest_id') or move.location_id.id,
            'picking_type_id': return_picking.picking_type_id.id,
            'warehouse_id': return_picking.picking_type_id.warehouse_id.id,
            'origin_returned_move_id': move.id,
            'procure_method': 'make_to_stock',
            'move_dest_id': False,
        })
        if return_picking:
            return_picking.action_confirm()
            return_picking.action_assign()
            wiz = return_picking.button_validate()
            res_id = wiz.get('res_id')
            wiz_obj = self.env['stock.immediate.transfer'].browse(res_id)
            wiz_obj.process()

    """
    Pass data Dictionary 
    param : data = {'location_id':Id,'location_dest_id':dest_location_id,'origin':source doc,
    'picking_type_id':pick_type_id,'product_id':product_id,'product_uom_qty':qty,
    'warehouse_id':warehouse_id}
    param : auto_validate = True/False
    picking_id,source_location_id,location_dest_id,
    datas={'product_id':qty,'product_id':qty,'product_id':qty}
    
    """

    def create_picking_ept(self, data, auto_validate=False):
        picking_obj = self.env['stock.picking']
        vals = {
            'move_lines': [],
            'location_id': data.get('location_id', ''),
            'location_dest_id': data.get('location_dest_id', ''),
            'origin': data.get('origin', ''),
            'picking_type_id': data.get('picking_type_id', ''),
            'state': 'draft',
        }
        new_picking = picking_obj.create(vals)
        vals = {
            'product_id': data.get('product_id', ''),
            'product_uom_qty': data.get('product_uom_qty', ''),
            'picking_id': new_picking.id,
            'state': 'draft',
            'location_id': data.get('location_id', ''),
            'location_dest_id': data.get('location_dest_id', ''),
            'picking_type_id': data.get('picking_type_id', ''),
            'warehouse_id': data.get('warehouse_id', ''),
            'procure_method': 'make_to_stock',
            'move_dest_id': False
        }
        move = self.env['stock.move'].create(vals)
        if move:
            new_picking.action_confirm()
            new_picking.action_assign()
        if auto_validate:
            wiz = new_picking.button_validate()
            res_id = wiz.get('res_id')
            wiz_obj = self.env['stock.immediate.transfer'].browse(res_id)
            wiz_obj.process()

    """
    Method Parameter :- picking id,order_line_field_key
    For Ex:- if use shopify shopify_line_id set in sale order line..
            use order_line_field_key = shopify_line_id
    For Ex:- picking_id = 25
    This way call Method :-  self.env['stock.picking'].get_tracking_numbers(25,'shopify_line_id')
    Method return :- 
            {'default_code' :[{
                                'order_line_field_key':'',
                                'tracking_no':tracking_no,
                                'qty':qty
                                },
                              {
                                'order_line_field_key':'',
                                'tracking_no':tracking_no,
                                'qty':qty
                                }
                            ],
            'default_code' :[{
                                'order_line_field_key':'',
                                'tracking_no':tracking_no,
                                'qty':qty
                            }],
            }
    
    """

    def get_traking_number_for_phantom_type_product(self, picking, order_line_field=False):
        line_items = {}
        update_move_ids = []
        move_obj = self.env['stock.move']
        picking_obj = self.env['stock.picking'].browse(picking)
        phantom_product_dict = {}
        move_lines = picking_obj.move_lines
        for move in move_lines:
            if move.sale_line_id.product_id.id != move.product_id.id:
                if move.sale_line_id in phantom_product_dict and \
                        move.product_id.id not in phantom_product_dict.get(move.sale_line_id):
                    phantom_product_dict.get(move.sale_line_id).append(move.product_id.id)
                else:
                    phantom_product_dict.update({move.sale_line_id: [move.product_id.id]})
        for sale_line_id, product_ids in phantom_product_dict.items():
            moves = move_obj.search([('picking_id', '=', picking_obj.id), ('state', '=', 'done'),
                                     ('product_id', 'in', product_ids)])
            line_id = sale_line_id.search_read([("id", "=", sale_line_id.id)], [order_line_field])[
                0].get(order_line_field)
            tracking_no = picking_obj.carrier_tracking_ref
            for move in moves:
                if not tracking_no:
                    for move_line in move.move_line_ids:
                        tracking_no = move_line.result_package_id \
                                      and move_line.result_package_id.tracking_no or False

            update_move_ids += moves.ids
            product_qty = sale_line_id.product_qty or 0.0
            default_code = sale_line_id.product_id.default_code
            if default_code in line_items:
                for line in line_items.get(default_code):
                    if tracking_no in line.get('tracking_no'):
                        quantity = line.get('quantity')
                        product_qty = quantity + product_qty
                        line.update({'quantity': product_qty, 'line_id': line_id,
                                     'tracking_no': tracking_no})
                else:
                    line_items.get(default_code).append(
                        {'quantity': product_qty, 'line_id': line_id, 'tracking_no': tracking_no})
            else:
                line_items.update({default_code: []})
                line_items.get(default_code).append(
                    {'quantity': product_qty, 'line_id': line_id, 'tracking_no': tracking_no})

        return line_items, update_move_ids

    def get_tracking_numbers(self, picking, order_line_field=False):
        move_line_obj = self.env['stock.move.line']
        line_items, update_move_ids = \
            self.get_traking_number_for_phantom_type_product(picking, order_line_field)
        stock_moves = self.env['stock.move'].search(
            [('id', 'not in', update_move_ids), ('picking_id', '=', picking)])
        for move in stock_moves:
            line_id = \
            move.sale_line_id.search_read([("id", "=", move.sale_line_id.id)], [order_line_field])[
                0].get(order_line_field)
            move_line = move_line_obj.search(
                [('move_id', '=', move.id), ('product_id', '=', move.product_id.id)])
            for move in move_line:
                if move.result_package_id:
                    tracking_no = False
                    if move.result_package_id.tracking_no:
                        tracking_no = move.result_package_id.tracking_no
                    product_qty = move.qty_done or 0.0
                    product_qty = int(product_qty)
                    default_code = move.product_id.default_code
                    if default_code in line_items:
                        for line in line_items.get(default_code):
                            if tracking_no in line.get('tracking_no'):
                                quantity = line.get('quantity')
                                product_qty = quantity + product_qty
                                line.update({'quantity': product_qty, 'line_id': line_id,
                                             'tracking_no': tracking_no})
                        else:
                            line_items.get(default_code).append(
                                {'quantity': product_qty, 'line_id': line_id,
                                 'tracking_no': tracking_no})
                    else:
                        line_items.update({default_code: []})
                        line_items.get(default_code).append(
                            {'quantity': product_qty, 'line_id': line_id,
                             'tracking_no': tracking_no})
        return line_items

    def send_to_shipper(self):
        """
        usage: If auto_processed_orders_ept = True passed in Context then we can not call send shipment from carrier
        This change is used in case of Import Shipped Orders for all connectors.
        @author: Keyur Kanani
        :return: True
        """
        context = dict(self._context)
        if context.get('auto_processed_orders_ept', False):
            return True
        else:
            return super(StockPicking, self).send_to_shipper()