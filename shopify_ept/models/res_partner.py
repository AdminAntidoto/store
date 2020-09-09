from odoo import models, fields, api
import logging
from datetime import datetime

_logger = logging.getLogger("shopify_customer_queue_process")


class res_partner(models.Model):
    _inherit = "res.partner"
    # company_name_ept = fields.Char("Company Of Name")
    # shopify_customer_id = fields.Char("Shopify Cutstomer Id")
    # shopify_instance_id = fields.Many2one('shopify.instance.ept', string='Shopify Instance')
    is_shopify_customer = fields.Boolean(string="Is Shopify Customer?",
                                     help="Used for identified that the customer is imported from Shopify store.")

    @api.model
    def create_shopify_pos_customer(self, order_response, log_book_id, instance):
        """
        Creates customer from POS Order.
        @author: Maulik Barad on Date 27-Feb-2020.
        """
        address = {}
        shopify_partner_obj = self.env["shopify.res.partner.ept"]
        customer_data = order_response.get("customer")

        if customer_data.get("default_address"):
            address = customer_data.get("default_address")

        customer_id = customer_data.get("id")
        first_name = customer_data.get("first_name") if customer_data.get("first_name") else ''
        last_name = customer_data.get("last_name") if customer_data.get("last_name") else ''
        phone = customer_data.get("phone")
        email = customer_data.get("email")

        shopify_partner = shopify_partner_obj.search([("shopify_customer_id", "=", customer_id),
                                                      ("shopify_instance_id", "=", instance.id)],
                                                      limit=1)
        name = ("%s %s" % (first_name, last_name)).strip()
        if name == "":
            if email:
                name = email
            elif phone:
                name = phone
        partner_vals = {
                "name": name,
                "phone": phone,
                "email": email,
                }

        if address.get("city"):
            state_name = address.get("province")
    
            country = self.env["res.country"].search(["|", ("name", "=", address.get("country")), ("code", "=", address.get("country_code"))])
            if not country:
                state = self.env["res.country.state"].search(["|", ("code", "=", address.get("province_code")), ("name", "=", state_name)], limit=1)
            else:
                state = self.env["res.country.state"].search(
                    ["|", ("code", "=", address.get("province_code")), ("name", "=", state_name), ("country_id", "=", country.id)],
                    limit=1)

            partner_vals.update({
                    "street": address.get("address1"),
                    "street2": address.get("address2"),
                    "city": address.get("city"),
                    "state_id":state.id or False,
                    "country_id":country.id or False,
                    "zip": address.get("zip"),
                })

        if shopify_partner:
            parent_id = shopify_partner.partner_id.id
            partner_vals.update(parent_id=parent_id)
            key_list = list(partner_vals.keys())
            res_partner = self._find_partner(partner_vals, key_list, [])
            if not res_partner:
                del partner_vals["parent_id"]
                key_list = list(partner_vals.keys())
                res_partner = self._find_partner(partner_vals, key_list, [])
                if not res_partner:
                    partner_vals.update({'is_company': False, 'type':'invoice', 'customer_rank':0, 'is_shopify_customer':True})
                    res_partner = self.create(partner_vals)
            return res_partner
        else:
            res_partner = self
            if email:
                res_partner = self.search([("email", "=", email)], limit=1)
            if not res_partner and phone:
                res_partner = self.search([("phone", "=", phone)], limit=1)
            if res_partner and res_partner.parent_id:
                res_partner = res_partner.parent_id

            if res_partner:
                partner_vals.update({"is_shopify_customer": True, "type":"invoice", "parent_id":res_partner.id})
                res_partner = self.create(partner_vals)
            else:
                key_list = list(partner_vals.keys())
                res_partner = self._find_partner(partner_vals, key_list, [])
                if res_partner:
                    res_partner.write({"is_shopify_customer": True})
                else:
                    partner_vals.update({"is_shopify_customer": True, "type":"contact"})
                    res_partner = self.create(partner_vals)
            
            shopify_partner_obj.create({"shopify_instance_id": instance.id,
                                        "shopify_customer_id": customer_id,
                                        "partner_id": res_partner.id})
            return res_partner

    @api.model
    def create_or_update_customer(self, vals, log_book_id, is_company=False, parent_id=False, type=False,
                                  instance=False, email=False, customer_data_queue_line_id=False,
                                  order_data_queue_line=False):
        partner_obj = self.env['res.partner']
        shopify_partner_obj = self.env['shopify.res.partner.ept']
        comman_log_line_obj = self.env["common.log.lines.ept"]
        state_obj = self.env['res.country.state']
        country_obj = self.env['res.country']
        if is_company:
            if order_data_queue_line:
                if vals.get('billing_address'):
                    address = vals.get('billing_address')
                    customer_id = vals.get('customer').get('id')
                    email = vals.get('customer').get('email')
                else:
                    message = 'Customer is skip because of the address was not found please verify customer in shopify ' \
                              'store'
                    model_id = comman_log_line_obj.get_model_id("sale.order")
                    comman_log_line_obj.shopify_create_order_log_line(message, model_id,
                                                                      order_data_queue_line, log_book_id)
                    order_data_queue_line and order_data_queue_line.write(
                        {'state': 'failed', 'processed_at': datetime.now()})

                    return False
            if customer_data_queue_line_id:
                # some time customer don't have any of address so we are by pass the customer
                if vals.get('default_address'):
                    address = vals.get('default_address')
                    customer_id = vals.get('id')
                    email = vals.get('email')
                else:
                    message = 'Customer is skip because of the address was not found please verify customer in shopify ' \
                              'store'
                    model_id = comman_log_line_obj.get_model_id("res.partner")
                    comman_log_line_obj.shopify_create_customer_log_line(message, model_id,
                                                                         customer_data_queue_line_id,
                                                                         log_book_id)
                    customer_data_queue_line_id and customer_data_queue_line_id.write({'state': 'failed',
                                                                                       'last_process_date': datetime.now()})

                    return False
            name = address.get('name') or "%s %s" % (address.get('first_name'), address.get('last_name'))
            # some time name is blank so we are write email as name in odoo
            if name == 'None None':
                name = email
            country = country_obj.search(["|", ('name', '=', address.get('country')), ('code', '=', address.get('country_code'))])
            state_name = address.get('province')
            if not country:
                state = state_obj.search(["|", ('code', '=', address.get('province_code')), ('name', '=', state_name)], limit=1)
            else:
                state = state_obj.search(
                    ["|", ('code', '=', address.get('province_code')), ('name', '=', state_name), ('country_id', '=', country.id)],
                    limit=1)
            partner_vals = {
                'name': name,
                'street': address.get('address1'),
                'street2': address.get('address2'),
                'city': address.get('city'),
                'state_code': address.get('province_code'),
                'state_name': state_name,
                'country_code': address.get('country_code'),
                'country_name': country,
                'phone': address.get('phone'),
                'email': email,
                'state_id':state.id or False,
                'zip': address.get('zip'),
                'country_id':country.id or False,
                'is_company': False,
            }

            partner_vals = partner_obj._prepare_partner_vals(partner_vals)
            partner_vals.update({'customer_rank': 1})
            res_partner_id = shopify_partner_obj.search(
                [('shopify_customer_id', '=', customer_id), ('shopify_instance_id', '=', instance.id)], limit=1)
            if res_partner_id:
                parent_id = res_partner_id.partner_id.id
                partner_vals.update({'parent_id': parent_id})
                key_list = ['name', 'state_id', 'city', 'zip', 'street', 'street2', 'country_id', 'email', 'parent_id']
                res_partner = partner_obj._find_partner(partner_vals, key_list, [])
                if not res_partner:
                    key_list = ['name', 'state_id', 'city', 'zip', 'street', 'street2', 'country_id', 'email']
                    res_partner = partner_obj._find_partner(partner_vals, key_list, [])
                    if not res_partner:
                        # here we are create child partner so its is_company is False
                        partner_vals.update({'is_company': False, 'type':'invoice', 'customer_rank':0, 'is_shopify_customer':True})

                        res_partner = partner_obj.create(partner_vals)
                        return res_partner
                    else:
                        if res_partner_id.partner_id.id == res_partner.id:
                            return res_partner_id.partner_id
                        else:
                            return res_partner
                else:
                    return res_partner
            else:
                key_list = ['name', 'state_id', 'city', 'zip', 'street', 'street2', 'country_id', 'email']
                res_partner = partner_obj._find_partner(partner_vals, key_list, [])
                if res_partner:
                    # here we need to discuss shopify customer id set in founded partner or not
                    # shopify_partner_obj.create({'shopify_instance_id': instance.id,
                    #                             'shopify_customer_id': customer_id,
                    #                             'partner_id': new_res_partner_id_3.id})
                    return res_partner
                else:
                    partner_vals.update({'is_shopify_customer': True, 'type':'contact'})
                    res_partner = partner_obj.create(partner_vals)
                    shopify_partner_obj.create({'shopify_instance_id': instance.id,
                                                'shopify_customer_id': customer_id,
                                                'partner_id': res_partner.id})
                    return res_partner
        else:
            company_name = vals.get("company")
            country = country_obj.search(["|", ('name', '=', vals.get('country')), ('code', '=', vals.get('country_code'))])
            state_name = vals.get('province')
            if not country:
                state = state_obj.search(["|", ('code', '=', vals.get('province_code')), ('name', '=', state_name)],
                                         limit=1)
            else:
                state = state_obj.search(
                    ["|", ('code', '=', vals.get('province_code')), ('name', '=', state_name),
                     ('country_id', '=', country.id)],
                    limit=1)
            partner_vals = {
                'name': vals.get('name'),
                'street': vals.get('address1'),
                'street2': vals.get('address2'),
                'city': vals.get('city'),
                'state_code': vals.get('province_code'),
                'state_name': vals.get('province'),
                'country_code': vals.get('country_code'),
                'country_name': vals.get('country'),
                'phone': vals.get('phone'),
                'email': email,
                'zip': vals.get('zip'),
                'parent_id': parent_id,
                'type': type,
                'state_id':state.id or False,
                'country_id': country.id or False,
            }
            partner_vals = partner_obj._prepare_partner_vals(partner_vals)
            partner_vals.update({'customer_rank': 0})
            key_list = ['name', 'state_id', 'city', 'zip', 'street', 'street2', 'country_id', 'email', 'parent_id']
            address_child = partner_obj._find_partner(partner_vals, key_list, [])
            if not address_child:
                key_list = ['name', 'state_id', 'city', 'zip', 'street', 'street2', 'country_id', 'email']
                address_parent = partner_obj._find_partner(partner_vals, key_list, [])
                if not address_parent:
                    address = partner_obj.create(partner_vals)
                    return address
                else:
                    return address_parent
            else:
                return address_child
