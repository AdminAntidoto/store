import base64
import requests
import hashlib
from odoo import models, fields, api
from odoo.exceptions import Warning


class ProductImageEpt(models.Model):
    _name = 'common.product.image.ept'
    _description = 'common.product.image.ept'
    _order = 'sequence, id'

    name = fields.Char(string='Name')
    product_id = fields.Many2one('product.product', string='Product', ondelete='cascade')
    template_id = fields.Many2one('product.template', string='Product template', ondelete='cascade')
    image = fields.Image("Image")
    url = fields.Char(string="Image URL", help="External URL of image")
    sequence = fields.Integer(help="Sequence of images.", index=True, default=10)
    image_binary = fields.Binary('Image Binary', help='Binary Image', attachment=True)

    @api.model
    def get_image(self, url):
        """
        Gets image from url.
        @author: Maulik Barad on Date 13-Dec-2019.
        @param url: URL added in field.
        @return: 
        """
        image_types = ["image/jpeg", "image/png", "image/tiff", "image/vnd.microsoft.icon", "image/x-icon",
                       "image/vnd.djvu", "image/svg+xml", "image/gif"]
        response = requests.get(url, stream=True, verify=False, timeout=10)
        if response.status_code == 200:
            if response.headers["Content-Type"] in image_types:
                image = base64.b64encode(response.content)
                if image:
                    return image
        raise Warning("Can't find image.\nPlease provide valid Image URL.")

    @api.model
    def create(self, vals):
        """
        Inherited for adding image from URL.
        @author: Maulik Barad on date 13-Dec-2019.
        """

        if not vals.get("image", False) and vals.get("url", ""):
            image = self.get_image(vals.get("url"))
            vals.update({"image": image})
        rec = super(ProductImageEpt, self).create(vals)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        rec_id = str(rec.id)
        url = base_url + '/lf/i/%s' % (base64.urlsafe_b64encode(rec_id.encode("utf-8")).decode(
            "utf-8"))
        rec.write({'url': url, 'image_binary': vals.get('image')})
        return rec
