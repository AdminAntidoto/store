import base64
import csv
import logging

from csv import DictWriter
from datetime import datetime
from io import StringIO, BytesIO

from odoo import models, fields
from odoo.exceptions import Warning, ValidationError

_logger = logging.getLogger("Shopify")


class PrepareProductForExport(models.TransientModel):
    """
    Model for adding Odoo products into Shopify Layer.
    @author: Maulik Barad on Date 11-Apr-2020.
    """
    _name = "shopify.prepare.product.for.export.ept"
    _description = "Prepare product for export in Shopify"

    export_method = fields.Selection([("csv", "Export in CSV file"),
                                      ("direct", "Export in Odoo Shopify Product List")], default="csv")
    shopify_instance_id = fields.Many2one("shopify.instance.ept")
    datas = fields.Binary("File")
    choose_file = fields.Binary(filters="*.csv", help="Select CSV file to upload.")
    file_name = fields.Char(string="File Name", help="Name of CSV file.")

    def prepare_product_for_export(self):
        """
        This method is used to export products in Shopify layer as per selection.
        If "direct" is selected, then it will direct export product into Shopify layer.
        If "csv" is selected, then it will export product data in CSV file, if user want to do some
        modification in name, description, etc. before importing into Shopify.
        """
        _logger.info("Starting product exporting via %s method..." % self.export_method)

        active_template_ids = self._context.get("active_ids", [])
        templates = self.env["product.template"].browse(active_template_ids)
        product_templates = templates.filtered(lambda template: template.type == "product")
        if not product_templates:
            raise Warning("It seems like selected products are not Storable products.")

        if self.export_method == "direct":
            return self.export_direct_in_shopify(product_templates)
        elif self.export_method == "csv":
            return self.export_csv_file(product_templates)

    def export_direct_in_shopify(self, product_templates):
        """
        Creates new product or updates existing product in Shopify layer.
        @author: Maulik Barad on Date 11-Apr-2020.
        """
        shopify_template_id = False
        sequence = 0

        shopify_templates = shopify_template_obj = self.env["shopify.product.template.ept"]
        shopify_product_obj = self.env["shopify.product.product.ept"]
        shopify_product_image_obj = self.env["shopify.product.image.ept"]

        variants = product_templates.product_variant_ids
        shopify_instance = self.shopify_instance_id

        for variant in variants:
            if not variant.default_code:
                continue
            product_template = variant.product_tmpl_id
            shopify_template = shopify_template_obj.search([
                ("shopify_instance_id", "=", shopify_instance.id),
                ("product_tmpl_id", "=", product_template.id)])

            if not shopify_template:
                shopify_product_template_vals = (
                    {"product_tmpl_id":product_template.id,
                     "shopify_instance_id":shopify_instance.id,
                     "shopify_product_category": product_template.categ_id.id,
                     "name": product_template.name,
                     "description": variant.description
                     })
                shopify_template = shopify_template_obj.create(shopify_product_template_vals)
                sequence = 1
                shopify_template_id = shopify_template.id
            else:
                if shopify_template_id != shopify_template.id:
                    shopify_product_template_vals = (
                        {"product_tmpl_id": product_template.id,
                         "shopify_instance_id": shopify_instance.id,
                         "shopify_product_category": product_template.categ_id.id,
                         "name": product_template.name,
                         "description": variant.description
                         })
                    shopify_template.write(shopify_product_template_vals)
                    shopify_template_id = shopify_template.id
            if shopify_template not in shopify_templates:
                shopify_templates += shopify_template

            # For adding all odoo images into shopify layer.
            shoify_product_image_list = []
            for odoo_image in product_template.ept_image_ids.filtered(lambda x: not x.product_id):
                shopify_product_image = shopify_product_image_obj.search_read(
                    [("shopify_template_id", "=", shopify_template_id),
                     ("odoo_image_id", "=", odoo_image.id)], ["id"])
                if not shopify_product_image:
                    shoify_product_image_list.append({
                        "odoo_image_id": odoo_image.id,
                        "shopify_template_id": shopify_template_id
                    })
            if shoify_product_image_list:
                shopify_product_image_obj.create(shoify_product_image_list)

            if shopify_template and shopify_template.shopify_product_ids and \
                    shopify_template.shopify_product_ids[
                        0].sequence:
                sequence += 1

            shopify_variant = shopify_product_obj.search([
                ("shopify_instance_id", "=", self.shopify_instance_id.id),
                ("product_id", "=", variant.id),
                ("shopify_template_id", "=", shopify_template_id)])
            shopify_variant_vals = ({
                "shopify_instance_id": shopify_instance.id,
                 "product_id": variant.id,
                 "shopify_template_id": shopify_template.id,
                 "default_code": variant.default_code,
                 "name": variant.name,
                 "sequence": sequence
                 })
            if not shopify_variant:
                shopify_variant = shopify_product_obj.create(shopify_variant_vals)
            else:
                shopify_variant.write(shopify_variant_vals)

            # For adding all odoo images into shopify layer.
            odoo_image = variant.ept_image_ids
            if odoo_image:
                shopify_product_image = shopify_product_image_obj.search_read(
                    [("shopify_template_id", "=", shopify_template_id),
                     ("shopify_variant_id", "=", shopify_variant.id),
                     ("odoo_image_id", "=", odoo_image[0].id)], ["id"])
                if not shopify_product_image:
                    shopify_product_image_obj.create({
                        "odoo_image_id": odoo_image[0].id,
                        "shopify_variant_id": shopify_variant.id,
                        "shopify_template_id": shopify_template_id,
                    })
        return True

    def export_csv_file(self, product_templates):
        """
        This method is used for export the odoo products in csv file format
        :param self: It contain the current class Instance
        @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 04/11/2019
        """
        buffer = StringIO()

        delimiter = ","
        field_names = ["template_name", "product_name", "product_default_code",
                       "shopify_product_default_code", "product_description",
                       "PRODUCT_TEMPLATE_ID", "PRODUCT_ID", "CATEGORY_ID"]
        csvwriter = DictWriter(buffer, field_names, delimiter=delimiter)
        csvwriter.writer.writerow(field_names)

        rows = []
        for template in product_templates:
            if len(template.attribute_line_ids) > 3:
                continue
            if len(template.product_variant_ids.ids) == 1 and not template.default_code:
                continue
            for product in template.product_variant_ids.filtered(lambda variant: variant.default_code):
                row = {
                    "PRODUCT_TEMPLATE_ID": template.id,
                   "template_name": template.name,
                   "CATEGORY_ID": template.categ_id.id,
                   "product_default_code": product.default_code,
                   "shopify_product_default_code":product.default_code,
                   "PRODUCT_ID": product.id,
                   "product_name": product.name,
                   "product_description": product.description or None,
                   }
                rows.append(row)

        if not rows:
            raise Warning("No data found to be exported.\n\nPossible Reasons:\n   - Number of "
                          "attributes are more than 3.\n   - SKU(s) are not set properly.")
        csvwriter.writerows(rows)
        buffer.seek(0)
        file_data = buffer.read().encode()
        self.write({
            "datas": base64.encodestring(file_data),
            "file_name": "Shopify_export_product"
        })

        return {
            "type": "ir.actions.act_url",
            "url": "web/content/?model=shopify.prepare.product.for.export.ept&id=%s&field=datas&field=datas&download=true&filename=%s.csv" % (
                self.id, self.file_name + str(datetime.now().strftime("%d/%m/%Y:%H:%M:%S"))),
            "target": self
        }

    def import_products_from_csv(self):
        """
        This method used to import product using csv file in shopify third layer
        images related changes taken by Maulik Barad
        @param : self
        @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 05/11/2019
        :return:
        """
        shopify_product_template = self.env["shopify.product.template.ept"]
        shopify_product_obj = self.env["shopify.product.product.ept"]
        common_log_obj = self.env["common.log.book.ept"]
        shopify_product_image_obj = self.env["shopify.product.image.ept"]
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id("shopify.process.import.export")

        if not self.choose_file:
            raise ValidationError("File Not Found To Import")
        if not self.file_name.endswith(".csv"):
            raise ValidationError("Please Provide Only .csv File To Import Product !!!")
        file_data = self.read_file()
        log_book_id = common_log_obj.create({"type": "export",
                                             "module": "shopify_ept",
                                             "shopify_instance_id": self.shopify_instance_id.id,
                                             "active": True})
        required_field = ["template_name", "product_name", "product_default_code",
                          "shopify_product_default_code", "product_description",
                          "PRODUCT_TEMPLATE_ID", "PRODUCT_ID", "CATEGORY_ID"]
        for required_field in required_field:
            if not required_field in file_data.fieldnames:
                raise Warning("Required Column Is Not Available In File")
        sequence = 0
        row_no = 1
        shopify_template_id = False
        for record in file_data:
            message = ""
            if not record["PRODUCT_TEMPLATE_ID"] or not record["PRODUCT_ID"] or not record[
                "CATEGORY_ID"]:
                message += "PRODUCT_TEMPLATE_ID Or PRODUCT_ID Or CATEGORY_ID Not As Per Odoo Product %s" % (
                    row_no)
                vals = {"message": message,
                        "model_id": model_id,
                        "log_line_id": log_book_id.id,
                        }
                common_log_line_obj.create(vals)
                continue
            shopify_template = shopify_product_template.search(
                [("shopify_instance_id", "=", self.shopify_instance_id.id),
                 ("product_tmpl_id", "=", int(record["PRODUCT_TEMPLATE_ID"]))])

            if not shopify_template:
                shopify_product_template_vals = (
                    {"product_tmpl_id": int(record["PRODUCT_TEMPLATE_ID"]),
                     "shopify_instance_id": self.shopify_instance_id.id,
                     "shopify_product_category": int(record["CATEGORY_ID"]),
                     "name": record["template_name"],
                     "description": record["product_description"]
                     })
                shopify_template = shopify_product_template.create(shopify_product_template_vals)
                sequence = 1
                shopify_template_id = shopify_template.id

            else:
                if shopify_template_id != shopify_template.id:
                    shopify_product_template_vals = (
                        {"product_tmpl_id": int(record["PRODUCT_TEMPLATE_ID"]),
                         "shopify_instance_id": self.shopify_instance_id.id,
                         "shopify_product_category": int(record["CATEGORY_ID"]),
                         "name": record["template_name"],
                         "description": record["product_description"]
                         })
                    shopify_template.write(shopify_product_template_vals)
                    shopify_template_id = shopify_template.id

            # For adding all odoo images into shopify layer.
            # if shopify_template_id != shopify_template.id:
            shoify_product_image_list = []
            product_template = shopify_template.product_tmpl_id
            for odoo_image in product_template.ept_image_ids.filtered(lambda x: not x.product_id):
                shopify_product_image = shopify_product_image_obj.search_read(
                    [("shopify_template_id", "=", shopify_template_id),
                     ("odoo_image_id", "=", odoo_image.id)], ["id"])
                if not shopify_product_image:
                    shoify_product_image_list.append({
                        "odoo_image_id": odoo_image.id,
                        "shopify_template_id": shopify_template_id
                    })
            if shoify_product_image_list:
                shopify_product_image_obj.create(shoify_product_image_list)

            if shopify_template and shopify_template.shopify_product_ids and \
                    shopify_template.shopify_product_ids[
                        0].sequence:
                sequence += 1
            shopify_variant = shopify_product_obj.search(
                [("shopify_instance_id", "=", self.shopify_instance_id.id), (
                    "product_id", "=", int(record["PRODUCT_ID"])),
                 ("shopify_template_id", "=", shopify_template.id)])
            if not shopify_variant:
                shopify_variant_vals = ({"shopify_instance_id": self.shopify_instance_id.id,
                                         "product_id": int(record["PRODUCT_ID"]),
                                         "shopify_template_id": shopify_template.id,
                                         "default_code": record["shopify_product_default_code"],
                                         "name": record["product_name"],
                                         "sequence": sequence
                                         })
                shopify_variant = shopify_product_obj.create(shopify_variant_vals)
            else:
                shopify_variant_vals = ({"shopify_instance_id": self.shopify_instance_id.id,
                                         "product_id": int(record["PRODUCT_ID"]),
                                         "shopify_template_id": shopify_template.id,
                                         "default_code": record["shopify_product_default_code"],
                                         "name": record["product_name"],
                                         "sequence": sequence
                                         })
                shopify_variant.write(shopify_variant_vals)
            row_no = +1
            # For adding all odoo images into shopify layer.
            product_id = shopify_variant.product_id
            odoo_image = product_id.ept_image_ids
            if odoo_image:
                shopify_product_image = shopify_product_image_obj.search_read(
                    [("shopify_template_id", "=", shopify_template_id),
                     ("shopify_variant_id", "=", shopify_variant.id),
                     ("odoo_image_id", "=", odoo_image[0].id)], ["id"])
                if not shopify_product_image:
                    shopify_product_image_obj.create({
                        "odoo_image_id": odoo_image[0].id,
                        "shopify_variant_id": shopify_variant.id,
                        "shopify_template_id": shopify_template_id,
                    })
        if not log_book_id.log_lines:
            log_book_id.unlink()
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def read_file(self):
        """
        This method reads .csv file
        @author: Nilesh Parmar @Emipro Technologies Pvt. Ltd on date 08/11/2019
        """
        self.write({"datas": self.choose_file})
        self._cr.commit()
        import_file = BytesIO(base64.decodestring(self.datas))
        file_read = StringIO(import_file.read().decode())
        reader = csv.DictReader(file_read, delimiter=",")
        return reader
