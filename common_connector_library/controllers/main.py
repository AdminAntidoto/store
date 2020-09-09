# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import base64
from odoo import http, _
from odoo.http import request


class Create_Image_Url(http.Controller):

    @http.route('/lf/i/<string:encodedimage>', type='http', auth='public')
    def create_image_url(self, encodedimage='', **kwargs):
        if len(encodedimage):
            try:
                decode_data = base64.urlsafe_b64decode(encodedimage)
                res_id = str(decode_data, "utf-8")
                status, headers, content = request.env['ir.http'].sudo().binary_content(
                    model='common.product.image.ept', id=res_id,
                    field='image_binary')
                content_base64 = base64.b64decode(content) if content else ''
                headers.append(('Content-Length', len(content_base64)))
                return request.make_response(content_base64, headers)
            except Exception as e:
                return request.not_found()
        return request.not_found()
