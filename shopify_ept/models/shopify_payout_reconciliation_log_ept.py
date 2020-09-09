# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from odoo import models, fields, api, _


class ShopifyPayoutReconciliationProcessLog(models.Model):
    _name = "shopify.payout.logline.ept"
    _description = "Shopify Reconciliation Process Log"
    _order = "id desc"

    payout_id = fields.Many2one("shopify.payout.report.ept", string="Payout ID")
    payout_transaction_ref = fields.Char(string="Payout Transaction ID")
    instance_id = fields.Many2one("shopify.instance.ept", string="Instance")
    message = fields.Char(string="Message")
    is_skipped = fields.Boolean(string="Skipped", default=False)

    def create_payout_schedule_activity(self, reconciliation_log_ids):
        """
        Use : Using this method Notify to user through the log and schedule activity.
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        :param job_id:
        :return: True
        """
        mail_activity_obj = self.env['mail.activity']
        ir_model_obj = self.env['ir.model']

        activity_type_id = reconciliation_log_ids[0].instance_id.shopify_activity_type_id.id
        date_deadline = datetime.strftime(
            datetime.now() + timedelta(days=int(reconciliation_log_ids[0].instance_id.shopify_date_deadline)),
            "%Y-%m-%d")
        model_id = ir_model_obj.search([('model', '=', 'shopify.payout.report.ept')])
        group_account_adviser = self.env.ref('account.group_account_manager')
        note = ''
        if not self._context.get('is_closed'):
            note = 'Bank statement lines not created for Payout Transaction Reference : '
            for log_line in reconciliation_log_ids.filtered(lambda line: line.is_skipped):
                note += str(log_line.payout_transaction_ref) + ' , '
        else:
            note = reconciliation_log_ids[0].message
        if note:
            for user_id in group_account_adviser.users:
                mail_activity = mail_activity_obj.search(
                    [('res_model_id', '=', model_id.id), ('user_id', '=', user_id.id), ('note', '=', note),
                     ('activity_type_id', '=', activity_type_id)])
                if mail_activity:
                    continue
                else:
                    vals = {'activity_type_id': activity_type_id,
                            'note': note,
                            'res_id': reconciliation_log_ids[0].payout_id.id,
                            'user_id': user_id.id or self._uid,
                            'res_model_id': model_id.id,
                            'date_deadline': date_deadline}
                    mail_activity_obj.create(vals)
        return True
