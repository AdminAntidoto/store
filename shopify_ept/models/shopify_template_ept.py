import base64
import hashlib
import json
import logging
import time
from datetime import datetime
import requests
from dateutil import parser
import pytz

utc = pytz.utc

from odoo import models, fields, api
from .. import shopify

_logger = logging.getLogger("Shopify_template_process")


class ProductCategory(models.Model):
    _inherit = "product.category"
    is_shopify_product_cat = fields.Boolean(
        string="This is used for an identity for is Shopify category or odoo category.if is True it means is Shopify category")


class ShopifyProductTemplateEpt(models.Model):
    _name = "shopify.product.template.ept"
    _description = 'Shopify Product Template Ept'

    name = fields.Char("Name")

    shopify_instance_id = fields.Many2one("shopify.instance.ept", "Instance")
    product_tmpl_id = fields.Many2one("product.template", "Product Template")
    active_template = fields.Boolean('Odoo Template Active', related="product_tmpl_id.active")
    shopify_tmpl_id = fields.Char("Shopify Tmpl Id")
    exported_in_shopify = fields.Boolean("Exported In Shopify")
    shopify_product_ids = fields.One2many("shopify.product.product.ept", "shopify_template_id",
                                          "Products")
    template_suffix = fields.Char("Template Suffix")
    created_at = fields.Datetime("Created At")
    updated_at = fields.Datetime("Updated At")
    published_at = fields.Datetime("Publish at")
    inventory_management = fields.Selection(
        [('shopify', 'Shopify tracks this product Inventory'),
         ('Dont track Inventory', "Don't track Inventory")],
        default='shopify')
    check_product_stock = fields.Boolean("Sale out of stock products ?", default=False)
    taxable = fields.Boolean("Taxable", default=True)
    fulfillment_service = fields.Selection(
        [('manual', 'Manual'), ('shopify', 'shopify'), ('gift_card', 'Gift Card')],
        default='manual')
    website_published = fields.Boolean(string="Published ?", default=False,
                                       copy=False)
    tag_ids = fields.Many2many("shopify.tags", "shopify_tags_rel", "product_tmpl_id", "tag_id",
                               "Tags")
    description = fields.Html("Description")
    total_variants_in_shopify = fields.Integer("Total Varaints",
                                               default=0)  # modify label name by Nilesh Parmar 20 dec 2019
    total_sync_variants = fields.Integer("Total Synced Variants", compute="get_total_sync_variants",
                                         store=True)  # modify label name by Nilesh Parmar 20 dec 2019
    shopify_product_category = fields.Many2one("product.category", "Product Category")
    active = fields.Boolean("Active", default=True)  # add by bhavesh jadav 13/12/2019

    shopify_image_ids = fields.One2many("shopify.product.image.ept",
                                        "shopify_template_id")  # add by Bhavesh Jadav 17/12/2019 for the images

    @api.depends('shopify_product_ids.exported_in_shopify', 'shopify_product_ids.variant_id')
    def get_total_sync_variants(self):
        """ This method used to cumpute the total sync variants. 
            @param : self,import_data_id,comman_log_id
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 07/10/2019.
        """
        for template in self:
            variants = template.shopify_product_ids.filtered(
                lambda
                    x: x if x.exported_in_shopify == True and x.variant_id != False else False)
            template.total_sync_variants = variants and len(variants) or 0

    def write(self, vals):
        """
        This method use to archive/unarchive shopify product variants base on shopify product templates.
        :parameter: self, vals
        :return: res
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 09/12/2019.
        :Task id: 158502
        """
        if 'active' in vals.keys():
            for shopify_template in self:
                shopify_template.shopify_product_ids and shopify_template.shopify_product_ids.write(
                    {'active': vals.get('active')})
                if vals.get('active'):
                    shopify_variants = self.env['shopify.product.product.ept'].search(
                        [('shopify_template_id', '=', shopify_template.id), ('shopify_instance_id', '=',
                                                                             shopify_template.shopify_instance_id.id),
                         ('active', '=', False)])
                    shopify_variants and shopify_variants.write({'active': vals.get('active')})
        res = super(ShopifyProductTemplateEpt, self).write(vals)
        return res

    @api.model
    def find_template_attribute_values(self, response_template, product_template, variant):
        """
        Author : Bhavesh Jadav  12/12/2019 for crate domain for the template attribute value  from the product.template.attribute.value
        response_template:use for the product template response from the shopify datatype should be dict
        product_template: use for the odoo product template
        variant: use for the product variant response from the shopify datatype should be dict
        return: template_attribute_value_domain data type list
        """
        template_attribute_value_domain = []
        product_attribute_list = []

        for attribute in response_template.get('options'):
            product_attribute = self.env['product.attribute'].search(
                [('name', '=ilike', attribute.get('name'))], limit=1)
            product_attribute_list.append(product_attribute)
        counter = 0
        for product_attribute in product_attribute_list:
            counter += 1
            attribute_name = 'option' + str(counter)
            attribute_val = variant.get(attribute_name)
            product_attribute_value = self.env['product.attribute.value'].search(
                [('attribute_id', '=', product_attribute.id), ('name', '=ilike', attribute_val)],
                limit=1)
            if product_attribute_value:
                template_attribute_value_id = self.env['product.template.attribute.value'].search(
                    [('product_attribute_value_id', '=', product_attribute_value.id),
                     ('attribute_id', '=', product_attribute.id),
                     ('product_tmpl_id', '=', product_template.id)], limit=1)
                if template_attribute_value_id:
                    domain = (
                        'product_template_attribute_value_ids', '=', template_attribute_value_id.id)
                    template_attribute_value_domain.append(domain)
        return template_attribute_value_domain

    def create_simple_odoo_product_template(self, instance, response_template, product_category, price):
        """
        Author:Bhavesh Jadav 18/12/2019 for create odoo template  and set sku
        instance: use for the shopify instance
        response_template: shopify product response
        """
        product_template_obj = self.env['product.template']
        shopify_product_obj = self.env['shopify.product.product.ept']
        sku = response_template.get('variants')[0].get('sku')
        barcode = response_template.get('variants')[0].get('barcode')
        template_title = response_template.get('title')
        available_odoo_products = {}
        product_template = False
        #  'barcode': barcode or False,
        _logger.info('Start process of simple template | shopify product(%s) and shopify product id(%s) create' % (
            response_template.get('title'), response_template.get('id')))
        if sku or barcode:
            vals = {'name': template_title,
                    'default_code': sku or False,
                    'type': 'product'}  # 'categ_id': product_category.id

            product_template = product_template_obj.create(vals)
            if barcode and product_template:
                product_template.product_variant_id.write({'barcode': barcode})
            shopify_product_obj.shopify_update_price(instance, product_template, price)
            available_odoo_products.update(
                {response_template.get('variants')[0]["id"]: product_template.product_variant_id})
        return product_template, available_odoo_products

    def shopify_sync_products(self, product_data_line_id, shopify_tmpl_id, instance, log_book_id,
                              order_data_line_id=False):
        """This is used to sync products.
            @author: Bhavesh Jadav@Emipro Technologies Pvt. Ltd on date 16/12/2019.
        """
        shopify_product_obj = self.env['shopify.product.product.ept']
        comman_log_line_obj = self.env["common.log.lines.ept"]
        product_category_obj = self.env['product.category']
        template_updated = False
        is_importable_checked = False
        model = "shopify.product.template.ept"
        model_id = comman_log_line_obj.get_model_id(model)
        instance.connect_in_shopify()
        set_in_template = True
        result = False
        is_data_line_process = False
        template_image_updated = False
        set_sku_barcode = False
        if shopify_tmpl_id and not product_data_line_id:
            try:
                result = [shopify.Product().find(shopify_tmpl_id)]
            except Exception as e:
                if e.response.code == 429 and e.response.msg == "Too Many Requests":
                    time.sleep(5)
                    result = [shopify.Product().find(shopify_tmpl_id)]
                elif order_data_line_id:
                    message = "Shopify product did not exist in Shopify store with product id: %s" % (
                        shopify_tmpl_id)
                    comman_log_line_obj.shopify_create_order_log_line(message, model_id,
                                                                      order_data_line_id,
                                                                      log_book_id)
                    order_data_line_id and order_data_line_id.write(
                        {'state': 'failed', 'processed_at': datetime.now()})
                    return True
                else:
                    return True
        if not result:
            response_template = product_data_line_id.synced_product_data
            response_template = json.loads(response_template)
        else:
            remove_dict_result = result.pop()
            response_template = remove_dict_result.to_dict()
        if not response_template:
            return True
        _logger.info('Start process of shopify product(%s) and shopify product id(%s) create' % (
            response_template.get('title'), response_template.get('id')))
        template_dic = self.shopify_prepare_template_dic(response_template)
        shopify_template = self.search(
            [('shopify_tmpl_id', '=', template_dic.get('shopify_tmpl_id')),
             ('shopify_instance_id', '=', instance.id)])
        available_shopify_products = {}
        available_odoo_products = {}
        ##############################################################
        # Need to discuss about the product category
        ##############################################################
        product_category = product_category_obj.search(
            [('name', '=', template_dic.get('product_type')),
             ('is_shopify_product_cat', '=', True)], limit=1)
        if not product_category:
            product_category = product_category_obj.create(
                {'name': template_dic.get('product_type'), 'is_shopify_product_cat': True})
        odoo_template = shopify_template.product_tmpl_id
        for variant in response_template.get(
                'variants'):  # here we are check shopify_product and odoo_product availability and prepare dict for link with template or create new variants
            shopify_product, odoo_product = self.shopify_search_odoo_product_variant(instance,
                                                                                     variant.get(
                                                                                         'sku', ''),
                                                                                     variant.get(
                                                                                         'id'), variant.get('barcode'),template_dic.get('shopify_tmpl_id'))
            if shopify_product:
                available_shopify_products.update({variant["id"]: shopify_product})
                shopify_template = shopify_product.shopify_template_id
            if odoo_product:
                available_odoo_products.update({variant["id"]: odoo_product})
                odoo_template = odoo_product.product_tmpl_id
                # If template update in shopify middle later so we need to avoid update template so we need to add
                # that condition
                # if not odoo_template:
                # odoo_template = odoo_product.product_tmpl_id

            shopify_product = odoo_product = False
        product_image_dict = {}
        for variant in response_template.get('variants'):
            variant_id = variant.get("id")
            product_sku = variant.get("sku")
            variant_price = variant.get('price')
            # variant_dic = self.shopify_prepare_variant_dic(variant)
            variant_info = {
                'shopify_instance_id': instance.id, 'variant_id': variant.get('id'),
                'sequence': variant.get('position'), 'default_code': variant.get('sku', ''),
                'inventory_item_id': variant.get('inventory_item_id'),
                'inventory_management': variant.get('inventory_management') if variant.get(
                    'inventory_management') == 'shopify' else 'Dont track Inventory',
                'taxable': variant.get('taxable'),
                #                 'fulfillment_service': variant.get('fulfillment_service'),
                'created_at': self.convert_shopify_date_into_odoo_format(variant.get('created_at')),
                'updated_at': self.convert_shopify_date_into_odoo_format(variant.get('updated_at')),
                'exported_in_shopify': True,
                'check_product_stock': variant.get('inventory_policy')
            }
            shopify_product = available_shopify_products.get(variant_id)
            odoo_product = available_odoo_products.get(variant_id)
            if shopify_product and not odoo_product:
                odoo_product = shopify_product.product_id
            ####################################
            # Need to discuss if odoo product found from the shopify_product but with  new attribute
            ###################################
            if not is_importable_checked:
                is_importable, message = self.is_product_importable(response_template, instance,
                                                                    odoo_product, shopify_product)
                if not is_importable and message:
                    if product_data_line_id:
                        comman_log_line_obj.shopify_create_product_log_line(message, model_id,
                                                                            product_data_line_id,
                                                                            log_book_id)
                        product_data_line_id and product_data_line_id.write({
                            'state': 'failed',
                            'last_process_date': datetime.now()
                        })
                        is_data_line_process = True
                    if order_data_line_id:
                        comman_log_line_obj.shopify_create_order_log_line(message, model_id,
                                                                          order_data_line_id,
                                                                          log_book_id)
                        order_data_line_id and order_data_line_id.write(
                            {'state': 'failed', 'processed_at': datetime.now()})
                        is_data_line_process = True
                    break
                else:
                    is_importable_checked = True
            if not shopify_product:
                if not shopify_template:
                    if not odoo_template and instance.auto_import_product:
                        ##########################################################
                        # Need to testing code here
                        ##################################################

                        # if the without variant product than we are received response of product with attribute name
                        # is 'Title' or attribute value is 'Default Title' so here we are add one condition if the
                        # product with single variant or the attribute name is 'Title' or attribute value is 'Default
                        # Title' then that product consider without variant and create simple product template in odoo
                        if response_template.get('options')[0].get('name') == 'Title' and \
                                response_template.get('options')[0].get('values') == ['Default Title'] and len(
                            response_template.get('variants')) == 1:
                            odoo_template, available_odoo_products = self.create_simple_odoo_product_template(instance,
                                                                                                              response_template,
                                                                                                              product_category,
                                                                                                              variant.get(
                                                                                                                  'price'))
                        else:
                            if not set_sku_barcode:
                                odoo_template, available_odoo_products = shopify_product_obj.shopify_create_variant_product(
                                    response_template, instance, variant.get('price'), product_category,
                                    product_data_line_id, False)
                                set_sku_barcode = True
                        # odoo_template, available_odoo_products = shopify_product_obj.shopify_create_variant_product(
                        #     response_template, instance, variant.get('price'), product_category,
                        #     product_data_line_id, False)
                    if not odoo_template:
                        message = "%s Template Not found for sku %s in Odoo." % (
                            response_template.get('title', ''), product_sku)
                        if product_data_line_id:
                            comman_log_line_obj.shopify_create_product_log_line(message, model_id,
                                                                                product_data_line_id,
                                                                                log_book_id)
                            product_data_line_id and product_data_line_id.write({
                                'state': 'failed',
                                'last_process_date': datetime.now()
                            })
                            is_data_line_process = True
                        if order_data_line_id:
                            comman_log_line_obj.shopify_create_order_log_line(message, model_id,
                                                                              order_data_line_id,
                                                                              log_book_id)
                            order_data_line_id and order_data_line_id.write(
                                {'state': 'failed', 'processed_at': datetime.now()})
                            is_data_line_process = True
                        break
                    shopify_template = self.create_or_update_shopify_template(instance,
                                                                              template_dic,
                                                                              variant_info,
                                                                              response_template,
                                                                              odoo_product,
                                                                              product_category=product_category,
                                                                              shopify_template=False)
                    shopify_template.write({'product_tmpl_id': odoo_template.id})
                    template_updated = True
                odoo_product = available_odoo_products.get(variant_id)
                if not odoo_product:
                    if not instance.auto_import_product:
                        message = "Product %s Not found for sku %s in Odoo." % (
                            response_template.get('title', ''), product_sku)
                        if product_data_line_id:
                            comman_log_line_obj.shopify_create_product_log_line(message, model_id,
                                                                                product_data_line_id,
                                                                                log_book_id)
                            product_data_line_id and product_data_line_id.write({
                                'state': 'failed',
                                'last_process_date': datetime.now()
                            })
                            is_data_line_process = True
                        if order_data_line_id:
                            comman_log_line_obj.shopify_create_order_log_line(message, model_id,
                                                                              order_data_line_id,
                                                                              log_book_id)
                            order_data_line_id and order_data_line_id.write(
                                {'state': 'failed', 'processed_at': datetime.now()})
                            is_data_line_process = True
                        continue
                    if odoo_template.attribute_line_ids:
                        shopify_attribute_ids = []
                        odoo_attributes = odoo_template.attribute_line_ids.attribute_id.ids
                        for attribute in response_template.get('options'):
                            attribute = self.env["product.attribute"].get_attribute(
                                attribute["name"])
                            shopify_attribute_ids.append(attribute.id)
                        shopify_attributes = self.env["product.attribute"].search(
                            [("id", "in", shopify_attribute_ids)]).ids
                        shopify_attributes.sort()
                        ###########################################################################
                        # Need To discuss
                        #########################################################################
                        if odoo_attributes != shopify_attributes or len(odoo_attributes) != len(
                                response_template.get('options')):
                            message = "Product %s has tried to add new attribute for sku %s in Odoo." % (
                                response_template.get('title', ''), product_sku)
                            if product_data_line_id:
                                comman_log_line_obj.shopify_create_product_log_line(message,
                                                                                    model_id,
                                                                                    product_data_line_id,
                                                                                    log_book_id)
                                product_data_line_id and product_data_line_id.write({
                                    'state': 'failed',
                                    'last_process_date': datetime.now()
                                })
                                is_data_line_process = True
                                if instance.is_shopify_create_schedule:
                                    self.env[
                                        'shopify.product.data.queue.ept'].create_schedule_activity_for_product(
                                        queue_line=product_data_line_id, from_sale=False)
                                _logger.info(
                                    "Product {0} has tried to add new attribute for sku {1} of Queue {2} in Odoo. Please check activity for this.".format(
                                        response_template.get('title', ''), product_sku,
                                        product_data_line_id))
                            if order_data_line_id:
                                comman_log_line_obj.shopify_create_order_log_line(message, model_id,
                                                                                  order_data_line_id,
                                                                                  log_book_id)
                                order_data_line_id and order_data_line_id.write(
                                    {'state': 'failed', 'processed_at': datetime.now()})
                                is_data_line_process = True
                                if instance.is_shopify_create_schedule:
                                    self.env[
                                        'shopify.product.data.queue.ept'].create_schedule_activity_for_product(
                                        queue_line=order_data_line_id, from_sale=True)
                            break
                        else:
                            ##########################################################################################
                            # here need verify code
                            ##########################################################################################
                            counter = 0
                            for shopify_attribute in response_template.get('options'):
                                counter += 1
                                attribute_name = 'option' + str(counter)
                                attributes_value = variant.get(attribute_name)
                                attribute_id = odoo_template.attribute_line_ids.filtered(
                                    lambda x: x.display_name == shopify_attribute.get('name'))
                                attrib_value_id = self.env[
                                    'product.attribute.value'].get_attribute_values(
                                    attributes_value,
                                    attribute_id.attribute_id.id,
                                    auto_create=True).id
                                attribute_line = odoo_template.attribute_line_ids.filtered(
                                    lambda x: x.attribute_id.id == attribute_id.attribute_id.id)
                                if not attrib_value_id in attribute_line.value_ids.ids:
                                    attribute_line.value_ids = [(4, attrib_value_id, False)]
                            template_attribute_value_domain = self.find_template_attribute_values(
                                response_template, odoo_template, variant)
                            template_attribute_value_domain.append(
                                ('product_tmpl_id', '=', odoo_template.id))
                            odoo_product = self.env["product.product"].search(
                                template_attribute_value_domain)
                            odoo_product.default_code = variant["sku"]
                            odoo_product.barcode = variant['barcode'] or False
                    else:
                        ###################################################################
                        # here need to discuss one case default title attribute and value
                        ###################################################################
                        self.env["product.template"].create({
                            "name": response_template.get(
                                'title', ''),
                            "type": "product",
                            "default_code": variant["sku"],
                            "barcode": variant.get('barcode') or False,
                            "description_sale": variant.get(
                                "description", "")
                        })
                        odoo_product = self.env["product.product"].search(
                            [("default_code", "=", variant["sku"])])
                        if not odoo_product:
                            odoo_product = self.env["product.product"].search(
                                [("barcode", "=", variant["barcode"])])

                variant_info.update(
                    {"product_id": odoo_product.id, "shopify_template_id": shopify_template.id,
                     "name": odoo_product.name})
                #                 variant_info.pop('fulfillment_service')
                variant_info.pop('taxable')
                shopify_product = self.env["shopify.product.product.ept"].create(variant_info)
            else:
                if not template_updated:
                    self.create_or_update_shopify_template(instance, template_dic, variant_info,
                                                           response_template, odoo_product,
                                                           shopify_template, product_category)
                    template_updated = True
                #                 variant_info.pop('fulfillment_service')
                variant_info.pop('taxable')
                shopify_product.write(variant_info)
            self.update_variant_price(shopify_product, variant_price)
            # if instance.sync_product_with_images:
            #     if not shopify_template.product_tmpl_id.image_1920:
            #         set_in_template = False
            #     self.env['common.product.image.ept'].shopify_sync_product_images(instance,
            #                                                                      response_template,
            #                                                                      shopify_template,
            #                                                                      shopify_product,
            #                                                                      template_image_updated,
            #                                                                      set_in_template)
            #     template_image_updated = True'

            if not is_data_line_process:
                if shopify_template and product_data_line_id:
                    product_data_line_id.write({
                        'state': 'done',
                        'last_process_date': datetime.now()
                    })
                elif product_data_line_id:
                    product_data_line_id.write({
                        'state': 'failed',
                        'last_process_date': datetime.now()
                    })
        if instance.sync_product_with_images:
            shopify_template.shopify_sync_product_images(response_template)

        return shopify_template if shopify_template else False

    def shopify_sync_product_images(self, response_template):

        """
        Author: Bhavesh Jadav 18/12/2019
        This method use for sync image from store and the add refrence in shopify.product.image.ept
        param:instance:use for the shopify instance its type should be object
        param:response_template usr for the product response its type should be dict
        param:shopify_template use for the shopify template  its type should be object
        param:shopify_product use for the shopify product its type should be object
        param: template_image_updated its boolean for the manage update template image only one time

        @change: By Maulik Barad on Date 28-May-2020.
        When image was removed from Shopify and product is imported, the image was not removing from
        Shopify layer.
        Example : 1 image for template, removed it, imported the product and not removed in layer.
        So far, when no images were coming in response, those were not removing from layer.
        @version: Shopify 13.0.0.23
        """
        common_product_image_obj = self.env["common.product.image.ept"]
        shopify_product_image_obj = shopify_product_images = self.env["shopify.product.image.ept"]
        existing_common_template_images = {}
        is_template_image_set = True if self.product_tmpl_id.image_1920 else False
        for odoo_image in self.product_tmpl_id.ept_image_ids:
            if not odoo_image.image:
                continue
            key = hashlib.md5(odoo_image.image).hexdigest()
            if not key:
                continue
            existing_common_template_images.update({key: odoo_image.id})
        for image in response_template.get('images', {}):
            if image.get('src'):
                shopify_image_id = str(image.get('id'))
                url = image.get('src')
                variant_ids = image.get('variant_ids')

                if not variant_ids:
                    """For Template Images."""
                    shopify_product_image = shopify_product_image_obj.search(
                        [("shopify_template_id", "=", self.id),
                         ("shopify_variant_id", "=", False),
                         ("shopify_image_id", "=", shopify_image_id)])
                    if not shopify_product_image:
                        try:
                            response = requests.get(url, stream=True, verify=False, timeout=10)
                            if response.status_code == 200:
                                image = base64.b64encode(response.content)
                                key = hashlib.md5(image).hexdigest()
                                if key in existing_common_template_images.keys():
                                    shopify_product_image = shopify_product_image_obj.create(
                                        {"shopify_template_id": self.id,
                                         "shopify_image_id": shopify_image_id,
                                         "odoo_image_id": existing_common_template_images[key]})
                                else:
                                    if not self.product_tmpl_id.image_1920:
                                        self.product_tmpl_id.image_1920 = image
                                        common_product_image = self.product_tmpl_id.ept_image_ids.filtered(
                                            lambda x: x.image == self.product_tmpl_id.image_1920)
                                    else:
                                        common_product_image = common_product_image_obj.create(
                                            {"name": self.name,
                                             "template_id": self.product_tmpl_id.id,
                                             "image": image,
                                             "url": url})
                                    shopify_product_image = shopify_product_image_obj.search([
                                        ("shopify_template_id", "=", self.id),
                                        ("odoo_image_id", "=", common_product_image.id)])
                                    if shopify_product_image:
                                        shopify_product_image.shopify_image_id = shopify_image_id
                        except Exception:
                            pass
                    shopify_product_images += shopify_product_image

                else:
                    """For Variant Images."""
                    shopify_products = self.shopify_product_ids.filtered(lambda x: int(x.variant_id) in variant_ids)
                    for shopify_product in shopify_products:
                        existing_common_variant_images = {}
                        for odoo_image in shopify_product.product_id.ept_image_ids:
                            if not odoo_image.image:
                                continue
                            key = hashlib.md5(odoo_image.image).hexdigest()
                            if not key:
                                continue
                            existing_common_variant_images.update({key: odoo_image.id})

                        shopify_product_image = shopify_product_image_obj.search(
                            [("shopify_variant_id", "=", shopify_product.id),
                             ("shopify_image_id", "=", shopify_image_id)])
                        if not shopify_product_image:
                            try:
                                response = requests.get(url, stream=True, verify=False, timeout=10)
                                if response.status_code == 200:
                                    image = base64.b64encode(response.content)
                                    key = hashlib.md5(image).hexdigest()
                                    if key in existing_common_variant_images.keys():
                                        shopify_product_image = shopify_product_image_obj.create(
                                            {"shopify_template_id": self.id,
                                             "shopify_variant_id": shopify_product.id,
                                             "shopify_image_id": shopify_image_id,
                                             "odoo_image_id": existing_common_variant_images[key]})
                                    else:
                                        if not shopify_product.product_id.image_1920 or not is_template_image_set:
                                            shopify_product.product_id.image_1920 = image
                                            common_product_image = shopify_product.product_id.ept_image_ids.filtered(
                                                lambda x: x.image == shopify_product.product_id.image_1920)

                                        else:
                                            common_product_image = common_product_image_obj.create(
                                                {"name": self.name,
                                                 "template_id": self.product_tmpl_id.id,
                                                 "product_id": shopify_product.product_id.id,
                                                 "image": image,
                                                 "url": url})
                                        shopify_product_image = shopify_product_image_obj.search([
                                            ("shopify_template_id", "=", self.id),
                                            ("shopify_variant_id", "=", shopify_product.id),
                                            ("odoo_image_id", "=", common_product_image.id)])
                                        if shopify_product_image:
                                            shopify_product_image.shopify_image_id = shopify_image_id
                            except Exception:
                                pass
                        shopify_product_images += shopify_product_image

        all_shopify_product_images = shopify_product_image_obj.search([("shopify_template_id",
                                                                     "=", self.id)])
        need_to_remove = all_shopify_product_images - shopify_product_images
        need_to_remove.unlink()
        _logger.info("Images Updated for shopify {0}".format(self.name))
        return True

    @api.model
    def update_variant_price(self, shopify_product, variant_price):
        pricelist_item = self.env["product.pricelist.item"].search(
            [("pricelist_id", "=", shopify_product.shopify_instance_id.shopify_pricelist_id.id),
             ("product_id", "=", shopify_product.product_id.id)], limit=1)
        if pricelist_item:
            if pricelist_item.currency_id.id != shopify_product.shopify_template_id.product_tmpl_id.company_id.currency_id.id:
                variant_price = pricelist_item.currency_id.compute(float(variant_price),
                                                                   shopify_product.shopify_template_id.product_tmpl_id.company_id.currency_id)
            pricelist_item.write({"fixed_price": variant_price})
        else:
            shopify_product.shopify_instance_id.shopify_pricelist_id.write({
                "item_ids": [(0, 0,
                              {
                                  "applied_on": "0_product_variant",
                                  "product_id": shopify_product.product_id.id,
                                  "compute_price": "fixed",
                                  "fixed_price": variant_price
                              })]
            })

    def shopify_prepare_template_dic(self, response_template):
        """This method used to Prepare a shopify template dictionary.
            @param : self,response_template
            @return: template_dic
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 11/10/2019.
        """
        template_dic = {}
        template_dic.update({
            'template_title': response_template.get('title'),
            'created_at': self.convert_shopify_date_into_odoo_format(
                response_template.get('created_at')),
            'body_html': response_template.get('body_html'),
            'updated_at': self.convert_shopify_date_into_odoo_format(
                response_template.get('updated_at')),
            'tags': response_template.get('tags'),
            'product_type': response_template.get('product_type'),
            'published_at': self.convert_shopify_date_into_odoo_format(
                response_template.get('published_at')),
            'shopify_tmpl_id': response_template.get('id'),
        })
        if response_template.get('published_at'):
            template_dic.update({'website_published': True})
        else:
            template_dic.update({'website_published': False})

        return template_dic

    def prepare_shopify_template_variant_comman_vals(self, instance, shopify_template,
                                                     template_dic, variant_dic, variant_sequence):
        """This method used to Prepare a shopify comman vals for the shopify template and shopify variant.
            @param : self, instance, shopify_template,template_dic, variant_dic, variant_sequence
            @return: vals
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 12/12/2019.
            Task Id : 157350
        """
        vals = {}
        vals.update({
            'default_code': variant_dic.get('sku'),
            'variant_id': variant_dic.get('variant_id'),
            'shopify_template_id': shopify_template.id,
            'shopify_instance_id': instance.id,
            'created_at': template_dic.get('created_at'),
            'updated_at': template_dic.get('updated_at'),
            'exported_in_shopify': True,
            'sequence': variant_sequence,
            'inventory_item_id': variant_dic.get('inventory_item_id'),
        })
        return vals

    def convert_shopify_date_into_odoo_format(self, product_date):
        """
        This method used to convert shopify product date into odoo date time format
        :return shopify product date
        @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 2/11/2019
        """
        shopify_product_date = False
        if not product_date:
            return shopify_product_date
        # time_zone_remove = product_date.replace(product_date[19:], '')
        # shopify_product_date = datetime.strptime(time_zone_remove, "%Y-%m-%dT%H:%M:%S")
        shopify_product_date = parser.parse(product_date).astimezone(utc).strftime('%Y-%m-%d %H:%M:%S')
        return shopify_product_date
    def shopify_search_odoo_product_variant(self, shopify_instance, product_sku, variant_id, barcode, s_template_id):
        """
        Author: Bhavesh Jadav 10/12/2019 for find odoo and shopify product based on the variant_id(shopify) or default_code
        :param shopify_instance: It is the browsable object of shopify instance
        :param product_sku : It is the default code of product and its type is String
        :param variant_id : It is the id of the product variant and its type is Integer
        :return : It will returns the odoo product and shopify product if it is exists
        """
        odoo_product = self.env['product.product']
        shopify_product_obj = self.env['shopify.product.product.ept']
        shopify_product = shopify_product_obj.search(
            [('variant_id', '=', variant_id), ('shopify_instance_id', '=', shopify_instance.id)],
            limit=1)
        if shopify_instance.shopify_sync_product_with == 'sku' and product_sku:
            if not shopify_product:
                shopify_product = shopify_product_obj.search([('default_code', '=', product_sku), (
                    'shopify_instance_id', '=', shopify_instance.id), ('shopify_template_id.shopify_tmpl_id', '=',
                                                                       s_template_id)], limit=1)
            if not shopify_product:
                shopify_product = shopify_product_obj.search(
                    [('product_id.default_code', '=', product_sku),
                     ('shopify_instance_id', '=', shopify_instance.id), ('shopify_template_id.shopify_tmpl_id', '=',
                                                                       s_template_id)], limit=1)
            if not shopify_product:
                odoo_product = odoo_product.search([('default_code', '=', product_sku)], limit=1)
        if shopify_instance.shopify_sync_product_with == 'barcode' and barcode:
            # if not shopify_product:
            #     shopify_product = shopify_product_obj.search([('barcode', '=', barcode), (
            #         'shopify_instance_id', '=', shopify_instance.id)], limit=1)
            if not shopify_product:
                shopify_product = shopify_product_obj.search(
                    [('product_id.barcode', '=', barcode),
                     ('shopify_instance_id', '=', shopify_instance.id)], limit=1)
            if not shopify_product:
                odoo_product = odoo_product.search([('barcode', '=', barcode)], limit=1)
        if shopify_instance.shopify_sync_product_with == 'sku_or_barcode':
            if product_sku:
                if not shopify_product:
                    shopify_product = shopify_product_obj.search([('default_code', '=', product_sku), (
                        'shopify_instance_id', '=', shopify_instance.id)], limit=1)
            # if not shopify_product and barcode:
            #     shopify_product = shopify_product_obj.search([('barcode', '=', barcode), (
            #         'shopify_instance_id', '=', shopify_instance.id)], limit=1)
            if not shopify_product and product_sku:
                shopify_product = shopify_product_obj.search([('default_code', '=', product_sku), (
                    'shopify_instance_id', '=', shopify_instance.id)], limit=1)
            if not shopify_product and barcode:
                shopify_product = shopify_product_obj.search(
                    [('product_id.barcode', '=', barcode),
                     ('shopify_instance_id', '=', shopify_instance.id)], limit=1)
            if not shopify_product or product_sku:
                odoo_product = odoo_product.search([('default_code', '=', product_sku)], limit=1)
            if not odoo_product and not shopify_product or barcode:
                odoo_product = odoo_product.search([('default_code', '=', product_sku)], limit=1)
        return shopify_product, odoo_product


    def shopify_search_odoo_product(self, instance, sku, barcode):
        """This method used to search odoo product based on product configuration in res setting.Shopify => Configuration => Setting => Sync Product With
            @param : self,insatnce,sku,barcode
            @return: odoo_product
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 11/10/2019.
        """
        odoo_product_obj = self.env['product.product']
        odoo_product = False
        if instance.shopify_sync_product_with == 'barcode' and barcode:
            odoo_product = odoo_product_obj.search([('barcode', '=', barcode)], limit=1)
        if instance.shopify_sync_product_with == 'sku' and sku:
            odoo_product = odoo_product_obj.search([('default_code', '=', sku)], limit=1)
        if instance.shopify_sync_product_with == 'sku_or_barcode':
            if sku:
                odoo_product = odoo_product_obj.search([('default_code', '=', sku)], limit=1)
            if not odoo_product and barcode:
                odoo_product = odoo_product_obj.search([('barcode', '=', barcode)], limit=1)
        return odoo_product

    def create_or_update_shopify_template(self, instance, template_dict, variant_dic,
                                          response_template, odoo_product, shopify_template, product_category):
        """This method used to create a shopify template into Odoo.
            @param : self,instance,template_dict,variant_dic,shopify_template,response_template,odoo_product
            @return: shopify_template
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 11/10/2019.
        """
        shopify_tag_obj = self.env['shopify.tags']
        shopify_template = shopify_template or False
        vals = {}
        if template_dict.get('inventory_policy') == 'continue':
            vals.update({'check_product_stock': True})
        if template_dict.get('inventory_management') == 'shopify':
            vals.update({'inventory_management': 'shopify'})
        else:
            vals.update({'inventory_management': 'Dont track Inventory'})

        vals.update({
            'product_tmpl_id': odoo_product and odoo_product.product_tmpl_id.id,
            'shopify_instance_id': instance.id,
            'name': template_dict.get('template_title'),
            'shopify_tmpl_id': template_dict.get('shopify_tmpl_id'),
            #             'fulfillment_service': variant_dic.get('fulfillment_service'),
            'taxable': variant_dic.get('taxable'),
            'created_at': template_dict.get('created_at'),
            'updated_at': template_dict.get('updated_at'),
            'description': template_dict.get('body_html'),
            'published_at': template_dict.get('published_at'),
            'website_published': template_dict.get('website_published'),
            'exported_in_shopify': True,
            'total_variants_in_shopify': len(response_template.get('variants')),
            'shopify_product_category': product_category.id if product_category else False
        })
        list_of_tags = []
        sequence = 1
        for tag in template_dict.get('tags') and template_dict.get('tags').split(','):
            if not len(tag) > 0:
                continue
            shopify_tag = shopify_tag_obj.search([('name', '=', tag)], limit=1)
            sequence = shopify_tag and shopify_tag.sequence or 0
            if not shopify_tag:
                sequence = sequence + 1
                shopify_tag = shopify_tag_obj.create({'name': tag, 'sequence': sequence})
            list_of_tags.append(shopify_tag.id)
        vals.update({'tag_ids': [(6, 0, list_of_tags)]})
        if shopify_template:
            shopify_template.write(vals)
        else:
            shopify_template = self.create(vals)

        return shopify_template

    # def shopify_manage_inconstance_variants(self, response_template, variant, product_category,
    #                                         template_dic, variant_dic):
    #     """This method used to create odoo template while the manage the inconstance variants.
    #         @param : self,response_template, variant, product_category, template_dic, variant_dic
    #         @return: odoo_template
    #         @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 23/10/2019.
    #     """
    #     product_attribute_obj = self.env['product.attribute']
    #     product_attribute_value_obj = self.env['product.attribute.value']
    #     product_template_obj = self.env['product.template']
    #     odoo_template = False
    #     option_name = []
    #     variation_attributes = []
    #     attrib_line_vals = []
    #     for options in response_template.get('options'):
    #         attrib_name = options.get('name')
    #         attrib_name and option_name.append(attrib_name)
    #     option1 = variant.get('option1', False)
    #     option2 = variant.get('option2', False)
    #     option3 = variant.get('option3', False)
    #     if option1 and (option_name and option_name[0]):
    #         variation_attributes.append({"name": option_name[0], "option": option1})
    #     if option2 and (option_name and option_name[1]):
    #         variation_attributes.append({"name": option_name[1], "option": option2})
    #     if option3 and (option_name and option_name[2]):
    #         variation_attributes.append({"name": option_name[2], "option": option3})
    #     for variation_attribute in variation_attributes:
    #         attribute_val = variation_attribute.get('option')
    #         attribute_name = variation_attribute.get('name')
    #         product_attribute = product_attribute_obj.search([('name', '=ilike', attribute_name)],
    #                                                          limit=1)
    #         if not product_attribute:
    #             product_attribute = product_attribute_obj.create({'name': attrib_name})
    #         if product_attribute:
    #             product_attribute_value = product_attribute_value_obj.search(
    #                 [('attribute_id', '=', product_attribute.id), ('name', '=', attribute_val)],
    #                 limit=1)
    #             if not product_attribute_value:
    #                 attrib_value = product_attribute_value_obj.with_context(active_id=False).create(
    #                     {'attribute_id': product_attribute.id, 'name': attribute_val})
    #
    #         if product_attribute_value:
    #             attribute_line_ids_data = [0, False,
    #                                        {
    #                                            'attribute_id': product_attribute.id,
    #                                            'value_ids': [
    #                                                [6, False, product_attribute_value.ids]]
    #                                            }]
    #             attrib_line_vals.append(attribute_line_ids_data)
    #
    #     odoo_template = product_template_obj.create({
    #         'name': template_dic.get('template_title'),
    #         'default_code': variant_dic.get('sku'),
    #         'barcode': variant_dic.get('barcode'),
    #         'type': 'product',
    #         'attribute_line_ids': attrib_line_vals,
    #         'categ_id': product_category and product_category.id or False
    #         })
    #     return odoo_template

    def is_product_importable(self, result, instance, odoo_product, shopify_product):
        """
        If we will get any issue from this method then we need to improve.
        """
        shopify_skus = []
        shopify_barcodes = []
        odoo_skus = []
        odoo_barcodes = []
        product_sku_barcodes = []
        odoo_product_obj = self.env['product.product']
        variants = result.get('variants')
        template_title = result.get('title', '')
        template_id = result.get('id', '')
        product_count = len(variants)
        importable = True
        message = ""

        if not odoo_product and not shopify_product:
            for variantion in variants:
                sku = variantion.get("sku") or False
                barcode = variantion.get('barcode', '') or False
                sku and shopify_skus.append(sku)
                barcode and shopify_barcodes.append(barcode)
                product_sku_barcodes.append(
                    {"name": template_title, "sku": sku or '', "barcode": barcode or ''})
                # if barcode:
                #     odoo_product = odoo_product_obj.search([("barcode", "=", barcode)], limit=1)
                # if not odoo_product and sku:
                #     odoo_product = odoo_product_obj.search([("default_code", "=", sku)], limit=1)
                # if odoo_product and odoo_product.product_tmpl_id.product_variant_count > 1:
                #     message = "Total number of variants in shopify and odoo are not match or all the SKU(s) are not match or all the Barcode(s) are not match for Product: %s and ID: %s." % (
                #         template_title, template_id)
                #     importable = False
                #     return importable, message
            for product_sku_barcode in product_sku_barcodes:
                sku = product_sku_barcode.get("sku") or False
                barcode = product_sku_barcode.get("barcode") or False
                if not sku and not barcode:
                    message = "From the data received of the Shopify store, SKU(s) or  " \
                              "Barcode(s) " \
                              "are not set for all variants of Shopify Product: '%s' and ID: %s." \
                              % (template_title, template_id)
                    if product_count == 1:
                        message = "From the data received of the Shopify store, SKU or Barcode is not set in Shopify Product: '%s' and ID: " \
                                  "%s." % (template_title, template_id)
                    importable = False
                    return importable, message
                # add by Bhavesh Jadav 20/12/2019 if the barcode ist already exist in oodo
                if barcode:
                    duplicate_barcode = self.env['product.product'].search([('barcode', '=', barcode)])
                    if duplicate_barcode:
                        message = "Duplicate barcode found in Product: %s and ID: %s." % (
                            template_title, template_id)
                        importable = False
                        return importable, message
            total_shopify_sku = len(set(shopify_skus))
            if not len(shopify_skus) == total_shopify_sku:
                message = "Duplicate SKU found in Product: %s and ID: %s." % (
                    template_title, template_id)
                importable = False
                return importable, message
            total_shopify_barcodes = len(set(shopify_barcodes))
            if not len(shopify_barcodes) == total_shopify_barcodes:
                message = "Duplicate barcode found in Product: %s and ID: %s." % (
                    template_title, template_id)
                importable = False
                return importable, message

        if odoo_product:
            odoo_template = odoo_product.product_tmpl_id
            if not (product_count == 1 and odoo_template.product_variant_count == 1):
                if product_count == odoo_template.product_variant_count:
                    for shopify_prdct, odoo_prdct in zip(result.get('variants'),
                                                         odoo_template.product_variant_ids):
                        sku = shopify_prdct.get('sku') or False
                        barcode = shopify_prdct.get('barcode', '') or False
                        sku and shopify_skus.append(sku)
                        barcode and shopify_barcodes.append(barcode)
                        product_sku_barcodes.append(
                            {"name": template_title, "sku": sku or '', "barcode": barcode or ''})
                        odoo_prdct and odoo_prdct.default_code and odoo_skus.append(
                            odoo_prdct.default_code)
                        odoo_prdct and odoo_prdct.barcode and odoo_barcodes.append(
                            odoo_prdct.barcode)

                    shopify_skus = list(filter(lambda x: len(x) > 0, shopify_skus))
                    odoo_skus = list(filter(lambda x: len(x) > 0, odoo_skus))
                    shopify_barcodes = list(filter(lambda x: len(x) > 0, shopify_barcodes))
                    odoo_barcodes = list(filter(lambda x: len(x) > 0, odoo_barcodes))

                    for product_sku_barcode in product_sku_barcodes:
                        sku = product_sku_barcode.get("sku") or False
                        barcode = product_sku_barcode.get("barcode") or False
                        if not sku and not barcode:
                            message = "All SKU(s) or Barcode(s) are not set in Product: %s and ID: %s." % (
                                template_title, template_id)
                            importable = False
                            return importable, message

                    total_shopify_sku = len(set(shopify_skus))
                    if not len(shopify_skus) == total_shopify_sku:
                        message = "Duplicate SKU found in Product: %s and ID: %s." % (
                            template_title, template_id)
                        importable = False
                        return importable, message
                    total_shopify_barcodes = len(set(shopify_barcodes))
                    if not len(shopify_barcodes) == total_shopify_barcodes:
                        message = "Duplicate barcode found in Product: %s and ID: %s." % (
                            template_title, template_id)
                        importable = False
                        return importable, message

                    for sku in shopify_skus:
                        if sku not in odoo_skus:
                            message = "SKU not found in Odoo for Product: %s and SKU: %s." % (
                                template_title, sku)
                            importable = False
                            return importable, message
                    for barcode in shopify_barcodes:
                        if barcode not in odoo_barcodes:
                            message = "Barcode not found in Odoo for Product: %s and Barcode: %s." % (
                                template_title, barcode)
                            importable = False
                            return importable, message
                else:
                    return importable, message
                    # if instance.shopify_allow_inconstance_remote_variants:
                    #     return importable, message
                    # else:
                    #     message = "All SKU(s) or Barcode(s) not as per Odoo product in Product: %s and ID: %s." % (
                    #         template_title, template_id)
                    #     if product_count == 1:
                    #         message = "Product: %s and ID: %s is simple product in shopify but Odoo has it product as variant." % (
                    #             template_title, template_id)
                    #     importable = False
                    #     return importable, message

        if shopify_product:
            shopify_skus = []
            shopify_barcodes = []
            product_sku_variants = []
            for variantion in variants:
                variant_id = variantion.get("id") or False
                sku = variantion.get("sku") or False
                barcode = variantion.get('barcode', '') or False
                sku and shopify_skus.append(sku)
                barcode and shopify_barcodes.append(barcode)
                # add by Bhavesh Jadav 20/12/2019 if the barcode ist already exist in oodo
                if barcode:
                    duplicate_barcode = self.env['product.product'].search([('barcode', '=', barcode)])
                    if duplicate_barcode:
                        shopify_variant = self.env['shopify.product.product.ept'].search(
                            [('shopify_instance_id', '=', instance.id),
                             ('variant_id', '=', variant_id)])

                        if shopify_variant and shopify_variant.product_id and shopify_variant.product_id.id != duplicate_barcode.id:
                            message = "Duplicate barcode found in Product: %s and ID: %s." % (
                                template_title, template_id)
                            importable = False
                            return importable, message
                product_sku_barcodes.append(
                    {"name": template_title, "sku": sku or '', "barcode": barcode or ''})
                product_sku_variants.append(
                    {
                        "variant_id": variant_id, "name": template_title, "sku": sku or '',
                        "barcode": barcode or ''
                    })

            # # Add by Haresh Mori
            # # For Extra variant
            # odoo_products = False
            # odoo_products = []
            # if shopify_product and len(product_sku_barcodes) != shopify_product.shopify_template_id.total_variants_in_shopify:
            #     for product_sku_barcode in product_sku_barcodes:
            #         odoo_product = odoo_product_obj.search(
            #             [("default_code", "=", product_sku_barcode.get("sku"))],
            #             limit=1) or False
            #         if odoo_product:
            #             odoo_products.append(odoo_product)

            # Added by Priya Pal
            # For same variant id
            # if shopify_product.product_id.product_tmpl_id.product_variant_count != len(product_sku_barcodes):
            #     shopify_product_obj = self.env['shopify.product.product.ept']
            #     for product_sku_variant in product_sku_variants:
            #         shopify_product = shopify_product_obj.search(
            #             [("variant_id", "=", product_sku_variant.get("variant_id"))],
            #             limit=1) or False
            #         if shopify_product:
            #             message = "Product with Variant ID: %s Already link in odoo product for Product: %s and ID: %s." % (
            #                 shopify_product.variant_id, template_title, template_id)
            #             importable = False
            #             return importable, message
            total_shopify_sku = len(set(shopify_skus))
            if not len(shopify_skus) == total_shopify_sku:
                message = "Duplicate SKU found in Product %s and ID: %s." % (
                    template_title, template_id)
                importable = False
                return importable, message
            total_shopify_barcodes = len(set(shopify_barcodes))
            if not len(shopify_barcodes) == total_shopify_barcodes:
                message = "Duplicate Barcode found in Product %s and ID: %s." % (
                    template_title, template_id)
                importable = False
                return importable, message

        return importable, message

    def shopify_publish_unpublish_product(self):
        common_log_book_obj = self.env['common.log.book.ept']
        model_id = self.env["common.log.lines.ept"].get_model_id('shopify.product.template.ept')
        instance = self.shopify_instance_id
        instance.connect_in_shopify()
        log_book_id = common_log_book_obj.create({
            'type': 'export',
            'module': 'shopify_ept',
            'shopify_instance_id': instance.id,
            'active': True
        })
        if self.shopify_tmpl_id:
            try:
                new_product = shopify.Product.find(self.shopify_tmpl_id)
                if new_product:
                    new_product.id = self.shopify_tmpl_id
                    if self._context.get('publish') == 'shopify_unpublish':
                        new_product.published_scope = 'null'
                        new_product.published_at = None
                    else:
                        new_product.published_scope = 'web'
                        new_product.published_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                    result = new_product.save()
                    if result:
                        result_dict = new_product.to_dict()
                        updated_at = self.convert_shopify_date_into_odoo_format(result_dict.get('updated_at'))
                        if self._context.get('publish') == 'shopify_unpublish':
                            self.write({
                                'updated_at': updated_at, 'published_at': False,
                                'website_published': False
                            })
                        else:
                            published_at = self.convert_shopify_date_into_odoo_format(
                                result_dict.get('published_at'))
                            self.write({
                                'updated_at': updated_at,
                                'published_at': published_at,
                                'website_published': True
                            })
            except:
                message = "Template %s not found in shopify When Publish" % (self.shopify_tmpl_id)
                vals = {
                    'message': message,
                    'model_id': model_id,
                    'res_id': self.shopify_tmpl_id if self.shopify_tmpl_id else False,
                    'log_line_id': log_book_id.id if log_book_id else False,
                }
                self.env['common.log.lines.ept'].create(vals)

        if not log_book_id.log_lines:
            log_book_id.unlink()
