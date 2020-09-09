import logging
import time
from datetime import datetime
from odoo.exceptions import Warning
from .. import shopify

_logger = logging.getLogger('shopify_export_stock_process===(Emipro)===')

from odoo import models, fields, api


class ShopifyProductProductEpt(models.Model):
    _name = "shopify.product.product.ept"
    _description = 'Shopify Product Product Ept'
    _order = 'sequence'

    producturl = fields.Text("Product URL")
    sequence = fields.Integer("Position", default=1)
    name = fields.Char("Title")
    shopify_instance_id = fields.Many2one("shopify.instance.ept", "Instance", required=1)
    default_code = fields.Char("Default Code")
    product_id = fields.Many2one("product.product", "Product", required=1)
    active_product = fields.Boolean('Odoo Product Active', related="product_id.active")
    shopify_template_id = fields.Many2one("shopify.product.template.ept", "Shopify Template", required=1,
                                          ondelete="cascade")
    exported_in_shopify = fields.Boolean("Exported In Shopify")
    variant_id = fields.Char("Variant Id")
    fix_stock_type = fields.Selection([('fix', 'Fix'), ('percentage', 'Percentage')], string='Fix Stock Type')
    fix_stock_value = fields.Float(string='Fix Stock Value', digits=0)
    created_at = fields.Datetime("Created At")
    updated_at = fields.Datetime("Updated At")
    shopify_image_id = fields.Char("Shopify Image Id")
    inventory_item_id = fields.Char("Inventory Item Id")
    # Added_by_Haresh Mori 31/01/2019
    check_product_stock = fields.Selection(
        [('continue', 'Allow'), ('deny', 'Denied'), ('parent_product', 'Set as a Product Template')],
        default='parent_product',
        help='If true than customers are allowed to place an order for the product variant when it is out of stock.')
    inventory_management = fields.Selection(
        [('shopify', 'Shopify tracks this product Inventory'), ('Dont track Inventory', 'Dont track Inventory'),
         ('parent_product', 'Set as a Product Template')],
        default='parent_product',
        help="If you select 'Shopify tracks this product Inventory' than shopify tracks this product inventory.if select 'Dont track Inventory' then after we can not update product stock from odoo")
    active = fields.Boolean('Active', default=True)  # add by bhavesh jadav 13/12/2019

    shopify_image_ids = fields.One2many("shopify.product.image.ept",
                                        "shopify_variant_id")  # add by Bhavesh Jadav 17/12/209  for the variant images

    def toggle_active(self):
        """
        Archiving related shopify product template if there is only one active shopify product
        :parameter: self
        :return: res
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 09/12/2019.
        :Task id: 158502
        """
        with_one_active = self.filtered(lambda product: len(product.shopify_template_id.shopify_product_ids) == 1)
        for product in with_one_active:
            product.shopify_template_id.toggle_active()
        return super(ShopifyProductProductEpt, self - with_one_active).toggle_active()

    def shopify_search_product_varint_in_odoo(self, instance, barcode, sku):
        """This method used to search products based on the res configuration.
            @param : self,barcode,sku
            @return: shopify_product,odoo_product
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 09/10/2019.
        """
        odoo_product_obj = self.env['product.product']
        shopify_product = False
        odoo_product = False
        shopify_variant = False
        if not shopify_variant and instance.shopify_sync_product_with == 'barcode':
            if barcode:
                shopify_variant = self.search(
                    [('product_id.barcode', '=', barcode), ('shopify_instance_id', '=', instance.id)], limit=1)
            if not shopify_variant and barcode:
                odoo_product = odoo_product_obj.search([('barcode', '=', barcode)], limit=1)
        if not shopify_variant and instance.shopify_sync_product_with == 'sku':
            if sku:
                shopify_variant = self.search(
                    [('default_code', '=', sku), ('shopify_instance_id', '=', instance.id)], limit=1)
            if not shopify_variant and sku:
                odoo_product = odoo_product_obj.search([('default_code', '=', sku)], limit=1)
        if not shopify_variant and instance.shopify_sync_product_with == 'sku_or_barcode':
            if not shopify_variant and barcode:
                shopify_variant = self.search(
                    [('product_id.barcode', '=', barcode), ('shopify_instance_id', '=', instance.id)], limit=1)
            if not shopify_variant and barcode:
                odoo_product = odoo_product_obj.search([('barcode', '=', barcode)], limit=1)
            if not odoo_product and not shopify_variant and sku:
                shopify_variant = self.search(
                    [('default_code', '=', sku), ('shopify_instance_id', '=', instance.id)], limit=1)
                if not shopify_variant and sku:
                    odoo_product = odoo_product_obj.search([('default_code', '=', sku)], limit=1)
        return shopify_product, odoo_product

    def shopify_create_variant_product(self, result, instance, price, product_category, import_data_id,
                                       shopify_template):
        """This method used to search the attribute and attribute in Odoo and based on attribute it's created a product template and variant.
            @param : self,barcode,sku
            @return: Boolean
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 09/10/2019.
        """
        product_template_obj = self.env['product.template']

        template_title = result.get('title', '')
        attrib_line_vals = []

        attrib_line_vals = self.shopify_prepare_attribute_vals(result)
        if attrib_line_vals:
            product_template = product_template_obj.create({'name': template_title,
                                                            'type': 'product',
                                                            'attribute_line_ids': attrib_line_vals,
                                                            'description_sale': result.get('description', '')
                                                            })  # 'categ_id': product_category.id

            self.shopify_update_price(instance, product_template, price)
            available_odoo_products = self.shopify_set_variant_sku(result, product_template, instance,
                                                                   import_data_id)  # change by bhavesh jadav
            # change by bhavesh jadav
            if available_odoo_products and product_template:
                return product_template, available_odoo_products
        else:
            return False
        return True

    def shopify_prepare_attribute_vals(self, result):
        """This method use to prepare a attribute values list.
            @param : self, result
            @return: vals
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 22/10/2019.
        """
        product_attribute_obj = self.env['product.attribute']
        product_attribute_value_obj = self.env['product.attribute.value']
        attrib_line_vals = []
        for attrib in result.get('options'):
            attrib_name = attrib.get('name')
            attrib_values = attrib.get('values')
            attribute = product_attribute_obj.search([('name', '=ilike', attrib_name)], limit=1)
            if not attribute:
                attribute = product_attribute_obj.create({'name': attrib_name})
            attr_val_ids = []

            for attrib_vals in attrib_values:
                attrib_value = product_attribute_value_obj.search(
                    [('attribute_id', '=', attribute.id), ('name', '=', attrib_vals)], limit=1)
                if not attrib_value:
                    attrib_value = product_attribute_value_obj.with_context(active_id=False).create(
                        {'attribute_id': attribute.id, 'name': attrib_vals})
                attr_val_ids.append(attrib_value.id)

            if attr_val_ids:
                attribute_line_ids_data = [0, False,
                                           {'attribute_id': attribute.id, 'value_ids': [[6, False, attr_val_ids]]}]
                attrib_line_vals.append(attribute_line_ids_data)
        return attrib_line_vals

    def shopify_update_price(self, instance, product_template, price):
        """This method use set price in product and also set product price in pricelist.
            @param : self, result
            @return: vals
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 22/10/2019.
        """
        if instance.shopify_pricelist_id.currency_id.id == product_template.company_id.currency_id.id:
            product_template.write({'list_price': price.replace(",", ".")})
        else:
            instance_currency = instance.shopify_pricelist_id.currency_id
            product_company_currency = product_template.company_id.currency_id
            date = self._context.get('date') or fields.Date.today()
            company = self.env['res.company'].browse(self._context.get('company_id')) or self.env.company
            amount = instance_currency._convert(float(price), product_company_currency, company, date)
            product_template.write({'list_price': amount})

        return True

    def shopify_set_variant_sku(self, result, product_template, instance, import_data_id):
        """This method set the variant SKU based on the attribute and attribute value.
            @param : self, result, product_template, instance
            @return: True
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 10/10/2019.
        """
        product_attribute_obj = self.env['product.attribute']
        product_attribute_value_obj = self.env['product.attribute.value']
        product_template_attribute_value_obj = self.env['product.template.attribute.value']
        odoo_product_obj = self.env['product.product']
        available_odoo_products = {}  # add by bhavesh jadav

        for variation in result.get('variants'):
            template_attribute_value_id = False
            sku = variation.get('sku')
            price = variation.get('price')
            barcode = variation.get('barcode') or False
            if barcode and barcode.__eq__("false"):
                barcode = False
            template_attribute_value_ids = []
            domain = []
            odoo_product = False
            variation_attributes = []
            option_name = []
            for options in result.get('options'):
                attrib_name = options.get('name')
                attrib_name and option_name.append(attrib_name)

            option1 = variation.get('option1', False)
            option2 = variation.get('option2', False)
            option3 = variation.get('option3', False)
            if option1 and (option_name and option_name[0]):
                variation_attributes.append({"name": option_name[0], "option": option1})
            if option2 and (option_name and option_name[1]):
                variation_attributes.append({"name": option_name[1], "option": option2})
            if option3 and (option_name and option_name[2]):
                variation_attributes.append({"name": option_name[2], "option": option3})

            for variation_attribute in variation_attributes:
                attribute_val = variation_attribute.get('option')
                attribute_name = variation_attribute.get('name')
                product_attribute = product_attribute_obj.search([('name', '=ilike', attribute_name)], limit=1)
                if product_attribute:
                    product_attribute_value = product_attribute_value_obj.search(
                        [('attribute_id', '=', product_attribute.id), ('name', '=', attribute_val)], limit=1)
                if product_attribute_value:
                    template_attribute_value_id = product_template_attribute_value_obj.search(
                        [('product_attribute_value_id', '=', product_attribute_value.id),
                         ('attribute_id', '=', product_attribute.id), ('product_tmpl_id', '=', product_template.id)],
                        limit=1)
                    template_attribute_value_id and template_attribute_value_ids.append(template_attribute_value_id.id)

            for template_attribute_value in template_attribute_value_ids:
                tpl = ('product_template_attribute_value_ids', '=', template_attribute_value)
                domain.append(tpl)
            domain and domain.append(('product_tmpl_id', '=', product_template.id))
            if domain:
                odoo_product = odoo_product_obj.search(domain)
            odoo_product and odoo_product.write({'default_code': sku})
            odoo_product and available_odoo_products.update({variation["id"]: odoo_product})  # add by bhavesh jadav
            if barcode:
                existing_barcode_product = odoo_product_obj.search([('barcode', '=', barcode)], limit=1)
                if existing_barcode_product and existing_barcode_product.id != odoo_product.id:
                    odoo_product and odoo_product.write({'barcode': barcode})
                else:
                    odoo_product and odoo_product.write({'barcode': barcode})
                odoo_product and available_odoo_products.update({variation["id"]: odoo_product})  # add by bhavesh jadav
            if price:
                if instance.shopify_pricelist_id.currency_id.id == product_template.company_id.currency_id.id:
                    odoo_product and odoo_product.write({'list_price': price.replace(",", ".")})
                else:
                    instance_currency = instance.shopify_pricelist_id.currency_id
                    product_company_currency = product_template.company_id.currency_id
                    date = self._context.get('date') or fields.Date.today()
                    company = self.env['res.company'].browse(
                        self._context.get('company_id')) or self.env.company
                    amount = instance_currency._convert(float(price), product_company_currency,
                                                        company, date)
                    odoo_product and odoo_product.write({'list_price': amount})

        return available_odoo_products

    def shopify_export_products(self, instance, is_set_price, is_set_images, is_publish, is_set_basic_detail,
                                templates):
        """
        This method used to Export the shopify product from Odoo to Shopify.
        :param instance:
        :param is_set_price:
        :param is_set_images:
        :param is_publish:
        :param is_set_basic_detail:
        :return:
        @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 19/11/2019.
        """

        comman_log_obj = self.env["common.log.book.ept"]
        comman_log_line_obj = self.env["common.log.lines.ept"]
        model = "shopify.product.product.ept"
        model_id = comman_log_line_obj.get_model_id(model)
        instance.connect_in_shopify()
        vals = {'type': 'export',
                'module': 'shopify_ept',
                'shopify_instance_id': instance.id,
                'active': True}
        log_book_id = comman_log_obj.create(vals)
        for template in templates:
            new_product = shopify.Product()
            if is_set_basic_detail or is_publish:
                self.shopify_set_template_value_in_shopify_obj(new_product, template, is_publish, is_set_basic_detail)
            if is_set_basic_detail or is_set_price:
                variants = []
                info = {}
                for variant in template.shopify_product_ids:
                    variant_vals = self.shopify_prepare_variant_vals(instance, variant, is_set_price,
                                                                     is_set_basic_detail)
                    variants.append(variant_vals)
                new_product.variants = variants
                self.preapre_export_update_product_attribute_vals(template, new_product)
            result = new_product.save()
            if not result:
                message = "Product %s Is Not Export In Shopify Store while Export Product" % (template.name)
                self.shopify_export_product_log_line(message, model_id, log_book_id)
            if result:
                self.update_products_details_Shopify_third_layer(new_product, template, is_publish)
            if new_product and is_set_images:
                self.export_product_images(instance, shopify_template=template)
            self._cr.commit()
        if not log_book_id.log_lines:
            log_book_id.unlink()

    def shopify_export_product_log_line(self, message, model_id, log_book_id):
        comman_log_line_obj = self.env["common.log.lines.ept"]
        vals = {'message': message,
                'model_id': model_id,
                'log_line_id': log_book_id.id if log_book_id else False}
        comman_log_line_obj.create(vals)

    def preapre_export_update_product_attribute_vals(self, template, new_product):
        if len(template.shopify_product_ids) > 1:
            attribute_list = []
            attribute_position = 1
            product_attribute_line_obj = self.env['product.template.attribute.line']
            product_attribute_lines = product_attribute_line_obj.search(
                [('id', 'in', template.product_tmpl_id.attribute_line_ids.ids)], order="attribute_id")
            for attribute_line in product_attribute_lines:
                info = {}
                attribute = attribute_line.attribute_id
                values = []
                value_ids = attribute_line.value_ids.ids
                # for variant in template.shopify_product_ids:
                #     for value in variant.shopify_template_id.product_tmpl_id.attribute_line_ids:
                #         if value.value_ids in value_ids and value.id not in values:
                #             values.append(value.id)
                value_names = []
                for value in self.env['product.attribute.value'].browse(values):
                    value_names.append(value.name)
                for value in attribute_line.value_ids:
                    if value.id not in values:
                        value_names.append(value.name)

                info.update({'name': attribute.name or attribute.name, 'values': value_names,
                             'position': attribute_position})
                attribute_list.append(info)
                attribute_position = attribute_position + 1
                # if attribute_position > 3:
                #     break
            new_product.options = attribute_list

    def update_products_in_shopify(self, instance, is_set_price, is_set_images, is_publish, is_set_basic_detail,
                                   templates):
        """
        This method is used to Update product in shopify store.
        :param instance: shopify instance id.
        :param is_set_price: if true then update price in shopify store.
        :param is_set_images: if true then update image in shopify store.
        :param is_publish: if true then publice product in shopify web.
        :param is_set_basic_detail: if true then update product basic detail.
        :return:
        @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 15/11/2019.
        """
        comman_log_obj = self.env["common.log.book.ept"]
        comman_log_line_obj = self.env["common.log.lines.ept"]
        model = "shopify.product.product.ept"
        model_id = comman_log_line_obj.get_model_id(model)
        if not is_publish and not is_set_basic_detail and not is_set_price and not is_set_images:
            raise Warning("Please Select Any Option To Update Product")
        instance.connect_in_shopify()
        vals = {'type': 'export',
                'module': 'shopify_ept',
                'shopify_instance_id': instance.id,
                'active': True}
        log_book_id = comman_log_obj.create(vals)
        for template in templates:
            if not template.shopify_tmpl_id:
                continue
            try:
                new_product = shopify.Product().find(template.shopify_tmpl_id)
            except Exception as e:
                if e.response.code == 429 and e.response.msg == "Too Many Requests":
                    time.sleep(5)
                    new_product = shopify.Product().find(template.shopify_tmpl_id)
                else:
                    message = "Template %s not found in shopify When update Product" % (template.shopify_tmpl_id)
                    self.shopify_export_product_log_line(message, model_id, log_book_id)
                    continue

            if is_set_basic_detail or is_publish:
                self.shopify_set_template_value_in_shopify_obj(new_product, template, is_publish, is_set_basic_detail)
            if is_set_basic_detail or is_set_price:
                variants = []
                for variant in template.shopify_product_ids:
                    variant_vals = self.shopify_prepare_variant_vals(instance, variant, is_set_price,
                                                                     is_set_basic_detail)
                    variants.append(variant_vals)
                new_product.variants = variants
                self.preapre_export_update_product_attribute_vals(template, new_product)
            result = new_product.save()
            if result:
                self.update_products_details_Shopify_third_layer(new_product, template, is_publish)
            if is_set_images:
                self.update_product_images(instance, shopify_template=template)
            updated_at = datetime.now()
            if is_publish == 'publish_product':
                published_at = datetime.now()
                template.write({'published_at': published_at, 'website_published': True})
            if is_publish == 'unpublish_product':
                template.write({'published_at': False, 'website_published': False})
            template.write({'updated_at': updated_at})
            for variant in template.shopify_product_ids:
                variant.write({'updated_at': updated_at})
        if not log_book_id.log_lines:
            log_book_id.unlink()

    def shopify_set_template_value_in_shopify_obj(self, new_product, template, is_publish, is_set_basic_detail):
        """
        This methos is used to set the shopify product template values
        :param new_product: shopify product object
        :param template: shopify product template product template
        :param is_publish: if true then publish product in shop[ify store
        :param is_set_basic_detail: if true then set the basic detail in shopify product
        :return:
        @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 15/11/2019.
        """

        if is_publish == 'publish_product':
            published_at = datetime.utcnow()
            published_at = published_at.strftime("%Y-%m-%dT%H:%M:%S")
            new_product.published_at = published_at
            new_product.published_scope = 'web'
        elif is_publish == 'unpublish_product':
            new_product.published_at = None
            new_product.published_scope = 'null'

        if is_set_basic_detail:
            if template.description:
                new_product.body_html = template.description
            if template.product_tmpl_id.seller_ids:
                new_product.vendor = template.product_tmpl_id.seller_ids[0].display_name
            new_product.product_type = template.shopify_product_category.name
            new_product.tags = [tag.name for tag in template.tag_ids]
            if template.template_suffix:
                new_product.template_suffix = template.template_suffix
            new_product.title = template.name
        return True

    def shopify_prepare_variant_vals(self, instance, variant, is_set_price, is_set_basic_detail):
        """This method used to prepare variant vals for export product variant from
            shopify third layer to shopify store.
            @param : instance, variant, is_set_price
            @return: variant_vals 
            @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 15/11/2019.
        """
        variant_vals = {}
        if variant.variant_id:
            variant_vals.update({'id': variant.variant_id})
        if is_set_price:
            price = instance.shopify_pricelist_id.get_product_price(variant.product_id, 1.0, partner=False,
                                                                    uom_id=variant.product_id.uom_id.id)
            variant_vals.update({'price': float(price)})
        if is_set_basic_detail:
            variant_vals.update({'barcode': variant.product_id.barcode or '',
                                 'grams': int(variant.product_id.weight * 1000),
                                 'weight': (variant.product_id.weight),
                                 'weight_unit': 'kg',
                                 'requires_shipping': 'true', 'sku': variant.default_code,
                                 'taxable': variant.shopify_template_id.taxable and 'true' or 'false',
                                 'title': variant.name,
                                 })
            option_index = 0
            option_index_value = ['option1', 'option2', 'option3']
            attribute_value_obj = self.env['product.template.attribute.value']
            att_values = attribute_value_obj.search(
                [('id', 'in', variant.product_id.product_template_attribute_value_ids.ids)],
                order="attribute_id")
            for att_value in att_values:
                if option_index > 3:
                    continue
                variant_vals.update({option_index_value[option_index]: att_value.name})
                option_index = option_index + 1

        if variant.inventory_management == 'parent_product':
            if variant.shopify_template_id.inventory_management == 'shopify':
                variant_vals.update({'inventory_management': 'shopify'})
            else:
                variant_vals.update({'inventory_management': None})
        elif variant.inventory_management == 'shopify':
            variant_vals.update({'inventory_management': 'shopify'})
        else:
            variant_vals.update({'inventory_management': None})

        if variant.check_product_stock == 'parent_product':
            if variant.shopify_template_id.check_product_stock:
                variant_vals.update({'inventory_policy': 'continue'})
            else:
                variant_vals.update({'inventory_policy': 'deny'})
        elif variant.check_product_stock == 'continue':
            variant_vals.update({
                'inventory_policy': 'continue'
            })
        else:
            variant_vals.update({
                'inventory_policy': 'deny'
            })
        return variant_vals

    def update_products_details_Shopify_third_layer(self, new_product, template, is_publish):
        """
        this method is used to update the shopify product id, created date, update date,
        public date in shopify third layer
        :param new_product: shopify store product
        :param template: shopify template
        :param is_publish: if true then update public date of shopify product
        :return:
        @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 19/11/2019.
        """
        result_dict = new_product.to_dict()
        created_at = datetime.now()
        updated_at = datetime.now()
        tmpl_id = result_dict.get('id')
        total_variant = 1
        if result_dict.get('variants'):
            total_variant = len(result_dict.get('variants' or False))
        template_vals = {'created_at': created_at, 'updated_at': updated_at,
                         'shopify_tmpl_id': tmpl_id,
                         'exported_in_shopify': True,
                         'total_variants_in_shopify': total_variant
                         }
        if is_publish:
            template_vals.update({'published_at': datetime.now(), 'website_published': True})
        if not template.exported_in_shopify:
            template.write(template_vals)
        for variant_dict in result_dict.get('variants'):
            updated_at = datetime.now()
            created_at = datetime.now()
            inventory_item_id = variant_dict.get('inventory_item_id') or False
            variant_id = variant_dict.get('id')
            shopify_variant = template.shopify_search_odoo_product_variant(template.shopify_instance_id, variant_dict.get('sku'),
                                                         variant_id, variant_dict.get('barcode'),tmpl_id)[0]
            if shopify_variant and not shopify_variant.exported_in_shopify:
                shopify_variant.write({
                    'variant_id': variant_id,
                    'updated_at': updated_at,
                    'created_at': created_at,
                    'inventory_item_id': inventory_item_id,
                    'exported_in_shopify': True
                })

    def export_product_images(self, instance, shopify_template):
        """
        Author: Bhavesh Jadav  @Emipro Technologies Pvt. Ltd on date 18/12/2019.
        This method use for the export images in to shopify store
        :param instance: use for the shopify instance
        :param shopify_template: use for the shopify template
        """
        result = False
        instance.connect_in_shopify()
        if not shopify_template.shopify_image_ids:
            return False
        for image in shopify_template.shopify_image_ids:
            shopify_image = shopify.Image()
            shopify_image.product_id = shopify_template.shopify_tmpl_id
            shopify_image.attachment = image.odoo_image_id.image.decode('utf-8')
            if image.odoo_image_id.template_id and image.odoo_image_id.product_id:
                shopify_image.variant_ids = [int(image.shopify_variant_id.variant_id)]
            result = shopify_image.save()
            if result:
                image.write({'shopify_image_id': shopify_image.id})
        return True

    # def export_product_images(self, instance, shopify_template=False):
    #     """
    #     this method is used to export odoo products images to shopify product
    #     :param instance:
    #     :param shopify_template:
    #     :return:
    #     @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 16/11/2019.
    #     """
    #     if not shopify_template:
    #         return False
    #     product_image_object = self.env['common.product.image.ept']
    #     shopify_image = shopify.Image()
    #     product_template = shopify_template.product_tmpl_id
    #     if product_template.image_1920:
    #         shopify_image.product_id = shopify_template.shopify_tmpl_id
    #         shopify_image.attachment = product_template.image_1920.decode('utf-8')
    #         result = shopify_image.save()
    #         if result:
    #             image_record = product_template.ept_image_ids.filtered(lambda x: x.image == product_template.image_1920)
    #             if not image_record:
    #                 self.create_image_record(instance, shopify_image, shopify_template, product_template,False)
    #             elif image_record:
    #                 self.update_image_record(instance, shopify_image, shopify_template,image_record)
    #     for image in product_template.ept_image_ids:
    #         shopify_image = shopify.Image()
    #         if not image.image and not instance.is_image_url:
    #             continue
    #         if not shopify_image:
    #             continue
    #         if not image.shopify_image_id:
    #             shopify_image.attachment = image.image.decode('utf-8')
    #             shopify_image.product_id = shopify_template.shopify_tmpl_id
    #             result = shopify_image.save()
    #             if result:
    #                 vals = {'shopify_product_tmpl_id': shopify_template.id,
    #                         'shopify_image_id': shopify_image.id,
    #                         'shopify_instance_id': instance.id
    #                         }
    #                 image.write(vals)
    #
    #     for shopify_product in shopify_template.shopify_product_ids:
    #         for product in shopify_product.product_id:
    #             shopify_image = shopify.Image()
    #             if product.image_1920:
    #                 shopify_image.product_id = shopify_template.shopify_tmpl_id
    #                 shopify_image.attachment = product.image_1920.decode('utf-8')
    #                 shopify_image.variant_ids = [int(shopify_product.variant_id)]
    #                 result = shopify_image.save()
    #                 if result:
    #                     image_record = product.ept_image_ids.filtered(
    #                         lambda x: x.image == product.image_1920)
    #                     if not image_record:
    #                         self.create_image_record(instance, shopify_image, shopify_template, False,
    #                                                  product)
    #                     elif image_record:
    #                         self.update_image_record(instance, shopify_image, shopify_template,image_record)
    #             for image in product.ept_image_ids:
    #                 shopify_image = shopify.Image()
    #                 if not image.image and not instance.is_image_url:
    #                     continue
    #                 if not shopify_image:
    #                     continue
    #                 if not image.shopify_image_id:
    #                     shopify_image.attachment = image.image.decode('utf-8')
    #                     shopify_image.product_id = shopify_template.shopify_tmpl_id
    #                     shopify_image.variant_ids = [int(shopify_product.variant_id)]
    #                     result = shopify_image.save()
    #                     if result:
    #                         vals = {'shopify_product_tmpl_id': shopify_template.id,
    #                                 'shopify_image_id': shopify_image.id,
    #                                 'shopify_instance_id': instance.id
    #                                 }
    #                         image.write(vals)

    def create_image_record(self, instance, shopify_image, shopify_template, product_template, product):
        product_image_object = self.env['common.product.image.ept']
        vals = {'image': product_template.image_1920 if product_template else product.image_1920,
                'shopify_product_tmpl_id': shopify_template.id,
                'shopify_image_id': shopify_image.id,
                'shopify_instance_id': instance.id,
                'template_id': product_template and product_template.id or False,
                'product_id': product and product.id or False
                }
        product_template_image_id = product_image_object.create(vals)

    def update_image_record(self, instance, shopify_image, shopify_template, image_record):
        vals = {'shopify_product_tmpl_id': shopify_template.id,
                'shopify_image_id': shopify_image.id,
                'shopify_instance_id': instance.id
                }
        image_record.write(vals)

    def update_product_images(self, instance, shopify_template):
        """
        Author:Bhavesh Jadav 18/12/2019 for the update Shopify image if image is new then export image
        :param instance: use for the shopify instance
        :param shopify_template: use for the shopify template
        """
        if not shopify_template.shopify_image_ids:
            return False
        result = False
        shopify_images = False
        try:
            shopify_images = shopify.Image().find(product_id=int(shopify_template.shopify_tmpl_id))
        except Exception as e:
            if e.response.code == 429 and e.response.msg == "Too Many Requests":
                time.sleep(5)
                shopify_images = shopify.Image().find(product_id=shopify_template.shopify_tmpl_id)

        for image in shopify_template.shopify_image_ids:
            if not image.shopify_image_id:
                shopify_image = shopify.Image()
                shopify_image.product_id = shopify_template.shopify_tmpl_id
                shopify_image.attachment = image.odoo_image_id.image.decode('utf-8')
                if image.shopify_variant_id:
                    shopify_image.variant_ids = [int(image.shopify_variant_id.variant_id)]
                result = shopify_image.save()
                if result:
                    image.write({'shopify_image_id': shopify_image.id})
            else:
                ############################################
                # Need to discuss update binary data or not
                ############################################
                if not shopify_images:
                    continue
                for shop_image in shopify_images:
                    if int(image.shopify_image_id) == shop_image.id:
                        shopify_image = shop_image
                        shopify_image.attachment = image.odoo_image_id.image.decode('utf-8')
                        result = shopify_image.save()
        return True

    # def update_product_images(self, instance, shopify_template=False):
    #     """
    #     this method is used to update shopify product images
    #     :param instance: shopify instance id
    #     :param shopify_template: shopify template
    #     :return:
    #     @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 27/11/2019.
    #     """
    #     product_template = shopify_template.product_tmpl_id
    #     for image in product_template.ept_image_ids:
    #         shopify_image = False
    #         if not image.image and not instance.is_image_url:
    #             continue
    #         if image.shopify_image_id:
    #             try:
    #                 shopify_images = shopify.Image().find(product_id=int(shopify_template.shopify_tmpl_id))
    #             except Exception as e:
    #                 if e.response.code == 429 and e.response.msg == "Too Many Requests":
    #                     time.sleep(5)
    #                     shopify_images = shopify.Image().find(product_id=shopify_template.shopify_tmpl_id)
    #             if not shopify_images:
    #                 continue
    #             for shop_image in shopify_images:
    #                 if int(image.shopify_image_id) == shop_image.id:
    #                     shopify_image = shop_image
    #             shopify_image.attachment = image.image.decode('utf-8')
    #             result = shopify_image.save()
    #     for shopify_product in shopify_template.shopify_product_ids:
    #         for product in shopify_product.product_id:
    #             for image in product.ept_image_ids:
    #                 shopify_image = False
    #                 if image.shopify_image_id:
    #                     try:
    #                         shopify_images = shopify.Image().find(product_id=int(shopify_template.shopify_tmpl_id))
    #                     except Exception as e:
    #                         if e.response.code == 429 and e.response.msg == "Too Many Requests":
    #                             time.sleep(5)
    #                             shopify_images = shopify.Image().find(product_id=shopify_template.shopify_tmpl_id)
    #                     if not shopify_images:
    #                         continue
    #                     for shop_image in shopify_images:
    #                         if int(image.shopify_image_id) == shop_image.id:
    #                             shopify_image = shop_image
    #                     shopify_image.attachment = image.image.decode('utf-8')
    #                     result = shopify_image.save()

    @api.model
    def export_stock_in_shopify(self, instance=False, products=False):
        """
        Find products with below condition
            1. shopify_instance_id = instance.id
            2. exported_in_shopify = True
            3. product_id in products
        Find Shopify location for the particular instance
        Check export_stock_warehouse_ids is configured in location or not
        Get the total stock of the product with configured warehouses and update that stock in shopify location
        here we use InventoryLevel shopify API for export stock
        :param instance:
        :param products:
        :return:
        @author: Angel Patel @Emipro Technologies Pvt.
        :Task ID: 157407
        """
        log_line_array = []
        comman_log_line_obj = self.env["common.log.lines.ept"]
        model = "shopify.product.product.ept"
        product_obj = self.env['product.product']
        model_id = comman_log_line_obj.get_model_id(model)
        shopify_products = self.search(
            [('shopify_instance_id', '=', instance.id), ('exported_in_shopify', '=', True),
             ('product_id', 'in', products)])
        if not shopify_products:
            return True
        instance.connect_in_shopify()
        location_ids = self.env['shopify.location.ept'].search(
            [('instance_id', '=', instance.id)])
        if not location_ids:
            message = "Location not found for instance %s while update stock" % (instance.name)
            log_line_array = self.shopify_create_log(message, model_id, False, log_line_array)

        for location_id in location_ids:
            shopify_location_warehouse = location_id.export_stock_warehouse_ids or False
            if not shopify_location_warehouse:
                message = "No Warehouse found for Export Stock in Shopify Location: %s" % (location_id.name)
                log_line_array = self.shopify_create_log(message, model_id, False, log_line_array)
                continue

            product_ids = shopify_products.mapped('product_id')
            export_product_stock = self.check_stock_type(
                    instance,
                    product_ids,
                    product_obj,
                    location_id.export_stock_warehouse_ids)

            for shopify_product in shopify_products:
                # odoo_product = product_obj.browse(shopify_product.product_id.id)
                odoo_product = shopify_product.product_id
                if odoo_product.type == 'product':
                    if not shopify_product.inventory_item_id:
                        message = "Inventory Item Id did not found for Shopify Poduct Vatiant ID " \
                                  "%s with name %s for instance %s while Export stock" % (
                                      shopify_product.id, shopify_product.name, instance.name)
                        log_line_array = self.shopify_create_log(message, model_id, odoo_product, log_line_array)
                        continue

                    quantity = 0.0
                    quantity = [x['stock'] for i,x in enumerate(export_product_stock) if x['product_id']==shopify_product.product_id.id][0]
                    if not quantity:
                        for warehouse in location_id.export_stock_warehouse_ids:
                            quantity += product_obj.get_stock_ept(odoo_product, warehouse.id,
                                                                  shopify_product.fix_stock_type,
                                                                  shopify_product.fix_stock_value,
                                                                  instance.shopify_stock_field.name)
                            odoo_product.invalidate_cache()
                    try:
                        shopify.InventoryLevel.set(location_id.shopify_location_id, shopify_product.inventory_item_id,
                                                   int(quantity))
                    except Exception as e:
                        if e.response.code == 429 and e.response.msg == "Too Many Requests":
                            time.sleep(5)
                            shopify.InventoryLevel.set(location_id.shopify_location_id,
                                                       shopify_product.inventory_item_id,
                                                       int(quantity))
                            continue
                        else:
                            message = "Error while Export stock for Product ID: %s & Product Name: '%s' for instance: '%s'\nError: %s" % (
                                odoo_product.id, odoo_product.name, instance.name,
                                str(e.response.code) + " " + e.response.msg)
                            log_line_array = self.shopify_create_log(message, model_id, odoo_product, log_line_array)
                            continue

        if len(log_line_array) > 0:
            self.create_log(log_line_array, "export", instance)
        if self._context.get('queue_process') == 'export_stock':
            """In an instance when the export stock process calls from Shopify product template = > export stock action,
               we did not write the last stock update date because there are 5 product moment and 
             then we only export stock of 3 products and the remaining two products stock did not export. Then we export from the option of the wizard, but it will not export 2 product stock."""
            return True
        instance.write({'shopify_last_date_update_stock': datetime.now()})
        return True

    def check_stock_type(self, instance, product_ids, prod_obj, warehouse):
        """
        This Method relocates check type of stock.
        :param instance: This arguments relocates instance of Shopify.
        :param product_ids: This argumentes product listing id of odoo.
        :param prod_obj: This argument relocates product object of common connector.
        :param warehouse:This arguments relocates warehouse of shopify export location.
        :return: This Method return prouct listing stock.
        """
        prouct_listing_stock = False
        if product_ids:
            # prod_ids = prod_obj.browse(product_ids)
            if instance.shopify_stock_field.name == 'qty_available':
                prouct_listing_stock = prod_obj.get_qty_on_hand(warehouse, product_ids)
            elif instance.shopify_stock_field.name == 'virtual_available':
                prouct_listing_stock = prod_obj.get_forecated_qty(warehouse, product_ids)
        return prouct_listing_stock

    def import_shopify_stock(self, instance):
        """
        search shopify product with below condition
            1. shopify_instance_id = instance.id
            2. exported_in_shopify = True
        any is_shopify_product_adjustment is set to True in stock.inventory. Then cancel it first.
        Find the shopify locations
        Using shopify location call InventoryLevel shopify API
        Using API response create stock_inventory_line and stock_inventory with configured warehouse in location for import stock
        :param instance:
        :return:
        @author: Angel Patel @Emipro Technologies Pvt. Ltd.
        """
        comman_log_line_obj = self.env["common.log.lines.ept"]
        model = "shopify.product.product.ept"
        model_id = comman_log_line_obj.get_model_id(model)
        log_line_array = []
        templates = self.search([('shopify_instance_id', '=', instance.id), ('exported_in_shopify', '=', True)])
        invetory_adjustments = self.env['stock.inventory'].search(
            [('is_shopify_product_adjustment', '=', True), ('state', '!=', 'done')])
        for invetory_adjustment in invetory_adjustments:
            if not invetory_adjustment.state == 'cancel':
                invetory_adjustment.action_cancel_draft()
                invetory_adjustment.write({'state': 'cancel'})
        if templates:
            instance.connect_in_shopify()
            location_ids = self.env['shopify.location.ept'].search(
                [('legacy', '=', False), ('instance_id', '=', instance.id)])
            if not location_ids:
                message = "Location not found for instance %s while Import stock" % (instance.name)
                log_line_array = self.shopify_create_log(message, model_id, False, log_line_array)
                self.create_log(log_line_array, "import", instance)
                _logger.info(message)
                return False

            for location_id in location_ids:
                stock_inventory_array = []
                shopify_location_warehouse = location_id.import_stock_warehouse_id or False
                if not shopify_location_warehouse:
                    message = "No Warehouse found for Import Stock in Shopify Location: %s" % (location_id.name)
                    log_line_array = self.shopify_create_log(message, model_id, False, log_line_array)
                    _logger.info(message)
                    continue

                try:
                    inventory_levels = shopify.InventoryLevel.find(location_ids=location_id.shopify_location_id,
                                                                   limit=250)
                    if len(inventory_levels) >= 250:
                        inventory_levels = self.shopify_list_all_inventoryLevel(inventory_levels)
                except Exception as e:
                    message = "Error while import stock for instance %s\nError: %s" % (
                        instance.name, str(e.response.code) + " " + e.response.msg)
                    log_line_array = self.shopify_create_log(message, model_id, False, log_line_array)
                    _logger.info(message)
                    self.create_log(log_line_array, "import", instance)
                    return False
                _logger.info("Length of the total inventory item id : %s" % len(inventory_levels))
                for inventory_level in inventory_levels:
                    inventory_level = inventory_level.to_dict()
                    inventory_item_id = inventory_level.get('inventory_item_id')
                    qty = inventory_level.get('available')
                    shopify_product = self.env['shopify.product.product.ept'].search(
                        [('inventory_item_id', '=', inventory_item_id), ('exported_in_shopify', '=', True),
                         ('shopify_instance_id', '=', instance.id)], limit=1)
                    if shopify_product:
                        stock_inventory_line = {
                            'product_id': shopify_product.product_id,
                            'location_id': location_id.import_stock_warehouse_id.lot_stock_id.id,
                            'product_qty': qty
                        }
                        stock_inventory_array.append(stock_inventory_line)
                if len(stock_inventory_array) > 0:
                    inventory = self.env['stock.inventory'].create_stock_inventory(stock_inventory_array,
                                                                                   location_id.import_stock_warehouse_id.lot_stock_id,
                                                                                   False)
                    if inventory:
                        inventory_name = 'Inventory For Instance "%s" And Shopify Location "%s"' % (
                            (instance.name) + ' ' + datetime.now().strftime('%d-%m-%Y'), location_id.name)
                        inventory.is_shopify_product_adjustment = True
                        inventory.name = inventory_name
                        instance.inventory_adjustment_id = inventory.id

        if len(log_line_array) > 0:
            self.create_log(log_line_array, "import", instance)

        return True

    def shopify_list_all_inventoryLevel(self, result):
        """
            This method used to call the page wise data import for product stock from Shopify to Odoo.
            @param : self, result, shopify_location_id
            @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 21/12/2019.
            Modify by Haresh Mori on 28/12/2019 API and Pagination changes
        """
        sum_inventory_list = []
        catch = ""
        while result:
            page_info = ""
            sum_inventory_list += result
            link = shopify.ShopifyResource.connection.response.headers.get('Link')
            if not link or not isinstance(link, str):
                return sum_inventory_list
            for page_link in link.split(','):
                if page_link.find('next') > 0:
                    page_info = page_link.split(';')[0].strip('<>').split('page_info=')[1]
                    try:
                        result = shopify.InventoryLevel.find(page_info=page_info, limit=250)
                    except Exception as e:
                        if e.response.code == 429 and e.response.msg == "Too Many Requests":
                            time.sleep(5)
                            result = shopify.InventoryLevel.find(page_info=page_info, limit=250)
                        else:
                            raise Warning(e)
            if catch == page_info:
                break
        return sum_inventory_list

    def shopify_create_log(self, message=False, model_id=False, product=False, log_line_array=False):
        """
        Append all log_line vals and return log_line vals
        :param message:
        :param model_id:
        :param product:
        :param log_line_array:
        :return: log_line_array
        @author: Angel Patel @Emipro Technologies Pvt. Ltd on date 14/11/2019.
        @Task ID: 157623
        """
        log_line_vals = {
            'message': message,
            'model_id': model_id,
            'product_id': product and product.id or False,
            'default_code': product and product.default_code or False
        }
        log_line_array.append(log_line_vals)
        return log_line_array

    def create_log(self, log_line_array, type, instance):
        comman_log_obj = self.env["common.log.book.ept"]
        comman_log_obj.create({'type': type,
                               'module': 'shopify_ept',
                               'shopify_instance_id': instance.id if instance else False,
                               'active': True,
                               "log_lines": [(0, 0, log_line) for log_line in log_line_array]})
        return True

    class ShopifyTag(models.Model):
        _name = "shopify.tags"
        _description = 'Shopify Tags'

        name = fields.Char("Name", required=1)
        sequence = fields.Integer("Sequence", required=1)

    class ProductCategory(models.Model):
        _inherit = "product.category"
        is_shopify_product_cat = fields.Boolean('Is Shopify Product Category')
