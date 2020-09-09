from odoo import models
from odoo.addons.iap import jsonrpc
import requests
import ast

DEFAULT_ENDPOINT = 'https://iap.odoo.emiprotechnologies.com/'


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _prepare_partner_vals(self, vals):
        """
            This function prepare dictionary for the res.partner.
            @note: You need to prepare partner values and pass as dictionary in this function.
            @requires: name
            @param vals: {'name': 'emipro', 'street': 'address', 'street2': 'address',
                        'email': 'test@test.com'...}
            @return: values of partner as dictionary
        """
        partner_vals = {
            'name': vals.get('name'),
            'parent_id': vals.get('parent_id', False),
            'street': vals.get('street', ''),
            'street2': vals.get('street2', ''),
            'city': vals.get('city', ''),
            'state_id': vals.get('state_id', '') or False,
            'country_id': vals.get('country_id') or False,
            'phone': vals.get('phone', ''),
            'email': vals.get('email'),
            'zip': vals.get('zip', ''),
            'lang': vals.get('lang', False),
            'company_id': vals.get('company_id', False),
            'type': vals.get('type', False),
            'is_company': vals.get('is_company', False),
        }
        return partner_vals

    def _find_partner(self, vals, key_list=[], extra_domain=[]):
        """
        This function find the partner based on domain.
        This function map the keys of the key_list with the dictionary and create domain and
        if you have give the extra_domain so
        it will merge with _domain (i.e _domain = _domain + extra_domain).
        @requires: vals, key_list
        @param vals: i.e {'name': 'emipro', 'street': 'address', 'street2': 'address',
        'email': 'test@test.com'...}
        @param key_list: i.e ['name', 'street', 'street2', 'email',...]
        @param extra_domain: This domain for you can pass your own custom domain.
        i.e [('name', '!=', 'test')...]
        @return: partner object or False
        """
        if key_list and vals:
            _domain = [] + extra_domain
            for key in key_list:
                if not vals.get(key, False):
                    continue
                (key in vals) and _domain.append((key, '=', vals.get(key)))
            return _domain and self.search(_domain, limit=1) or False
        return False

    def search_partner_by_email(self, email):
        partner = self.search([('email', '=', email)])
        return partner

    def get_country(self, country_name_or_code):
        country = self.env['res.country'].search(
            ['|', ('code', '=', country_name_or_code), ('name', '=', country_name_or_code)],
            limit=1)
        return country

    """
    @author : Harnisha Patel
    @last_updated_on : 4/10/2019
    Modified the below method to set state from the api of zippopotam.
    """

    def create_order_update_state(self, country_code, state_name_or_code, zip_code,country_obj=False):
        if not country_obj:
            country = self.get_country(country_code)
        else:
            country = country_obj
        state = self.env['res.country.state'].search(
            ['|', ('name', '=', state_name_or_code), ('code', '=', state_name_or_code),
             ('country_id', '=', country.id)], limit=1)

        if not state:
            try:
                url = 'https://api.zippopotam.us/' + country_code + '/' + zip_code.split('-')[0]
                response = requests.get(url)
                response = ast.literal_eval(response.content.decode('utf-8'))
            except:
                return state 
            if response:
                state_obj = self.env['res.country.state']
                if not country:
                    country_obj = self.env['res.country']
                    country = country_obj.search([('name', '=', response.get('country')), (
                        'code', '=', response.get('country abbreviation'))])
                if not country:
                    country = country_obj.create({'name': response.get('country'),
                                                  'code': response.get('country abbreviation')})
                state = state_obj.search(
                    ['|', ('name', '=', response.get('places')[0].get('state')), ('code', '=', response.get('places')[0].get('state abbreviation')),
                     ('country_id', '=', country.id)], limit=1)
                if not state:
                    state = state_obj.create({
                        'name': response.get('places')[0].get('state'),
                        'code': response.get('places')[0].get('state abbreviation'),
                        'country_id': country.id
                    })
                return state
        else:
            return state
