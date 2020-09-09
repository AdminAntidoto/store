#!/usr/bin/python3
# -*- coding: utf-8 -*-
import logging
import requests
from odoo import models, fields, api, _
from odoo.exceptions import Warning
from datetime import datetime
import time
from odoo.addons.shopify_ept import shopify

_logger = logging.getLogger('Payout')


class ShopifyPaymentReportEpt(models.Model):
    _name = "shopify.payout.report.ept"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Shopify Payout Report"
    _order = 'id desc'

    name = fields.Char(size=256, string='Name')
    instance_id = fields.Many2one('shopify.instance.ept', string="Instance")
    payout_reference_id = fields.Char(string="Payout Reference ID",
                                      help="The unique identifier of the payout")
    payout_date = fields.Date(string="Payout Date", help="The date the payout was issued.")
    payout_transaction_ids = fields.One2many('shopify.payout.report.line.ept', 'payout_id',
                                             string="Payout transaction lines")
    reconciliation_log_ids = fields.One2many('shopify.payout.logline.ept', 'payout_id',
                                             string="Transaction log lines")
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  help="currency code of the payout.")
    amount = fields.Float(string="Total Amount", help="The total amount of the payout.")
    statement_id = fields.Many2one('account.bank.statement', string="Bank Statement")
    payout_status = fields.Selection(
        [('scheduled', 'Scheduled'), ('in_transit', 'In Transit'), ('paid', 'Paid'),
         ('failed', 'Failed'), ('canceled', 'Canceled')], string="Payout status",
        help="The transfer status of the payout. The value will be one of the following\n"
             "- Scheduled:  The payout has been created and had transactions assigned to it, but it has not yet been submitted to the bank\n"
             "- In Transit: The payout has been submitted to the bank for processing.\n"
             "- Paid: The payout has been successfully deposited into the bank.\n"
             "- Failed: The payout has been declined by the bank.\n"
             "- Canceled: The payout has been canceled by Shopify")
    state = fields.Selection([('draft', 'Draft'), ('partially_generated', 'Partially Generated'),
                              ('generated', 'Generated'), ('partially_processed', 'Partially Processed'),
                              ('processed', 'Processed'), ('closed', 'Closed')
                              ], string="Status", default="draft")
    is_skip_from_cron = fields.Boolean(string="Skip From Schedule Actions", default=False)

    def check_process_statement(self):
        """
        Use : Using this method visible/Inivisble the statement execution button.
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        """
        if self.payout_transaction_ids:
            if any(line.is_remaining_statement == True for line in self.payout_transaction_ids):
                all_statement_processed = False
            else:
                all_statement_processed = True
        return all_statement_processed

    def generate_remaining_bank_statement(self):
        """
        Use : Using this method user can able create remaining bank statement.
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        :return: True
        """
        bank_statement_line_obj = self.env['account.bank.statement.line']
        remaining_transaction_ids = self.payout_transaction_ids.filtered(lambda line: line.is_remaining_statement)
        for transaction in remaining_transaction_ids:
            order_id = transaction.order_id
            partner_obj = self.env['res.partner']
            partner = partner_obj._find_accounting_partner(order_id.partner_id)
            if transaction.transaction_type == 'charge':
                invoice_ids = order_id.invoice_ids.filtered(lambda l: l.state == 'posted' and l.type == 'out_invoice')
                if not invoice_ids:
                    continue
            if transaction.transaction_type == 'refund':
                invoice_ids = order_id.invoice_ids.filtered(lambda l: l.state == 'posted' and l.type == 'out_refund')
                if not invoice_ids:
                    continue
            payment_reference = False
            shopify_account_config_id = self.instance_id.transaction_line_ids.filtered(lambda l:l.transaction_type == transaction.transaction_type)
            account_id = shopify_account_config_id and shopify_account_config_id.account_id
            if transaction.transaction_type == 'charge':
                payment_reference = self.env['account.payment'].search([('invoice_ids', 'in',invoice_ids.ids),
                                                                        ('amount', '=',transaction.amount),
                                                                        ('payment_type', '=','inbound')], limit=1)
            if transaction.transaction_type == 'refund':
                payment_reference = self.env['account.payment'].search([('invoice_ids', 'in',invoice_ids.ids),
                                                                        ('amount', '=',-(transaction.amount)),
                                                                        ('payment_type', '=','outbound')], limit=1)
            if payment_reference:
                reference = payment_reference.name
            else:
                reference = invoice_ids.name or ''
            if transaction.amount:
                bank_line_vals = {
                    'name': order_id.name or transaction.transaction_type,
                    'ref': reference or '',
                    'partner_id': partner and partner.id,
                    'amount': transaction.amount,
                    'account_ept_id': account_id and account_id.id,
                    'statement_id': self.statement_id.id,
                    'shopify_order_ids': [(6, 0, order_id.ids)],
                    'shopify_transaction_id': transaction.transaction_id,
                    'shopify_transaction_type': transaction.transaction_type,
                }
                bank_statement_line_obj.create(bank_line_vals)
            transaction.write({'is_remaining_statement': False})

        if self.check_process_statement():
            state = 'generated'
        else:
            state = 'partially_generated'
        self.write({'state': state})
        return True

    def generate_bank_statement(self):
        """
        Use : Using this method user can able to create bank statement.
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        :return: True
        """
        bank_statement_obj = self.env['account.bank.statement']
        partner_obj = self.env['res.partner']
        bank_statement_line_obj = self.env['account.bank.statement.line']
        payout_logline_obj = self.env['shopify.payout.logline.ept']
        account_invoice_obj = self.env['account.move']
        journal = self.instance_id.shopify_settlement_report_journal_id
        if not journal:
            message_body = "You have not configured Payout report Journal in " \
                           "Instance.\nPlease configured it from Setting"
            if self._context.get('is_cron'):
                self.message_post(body=_(message_body))
                self.is_skip_from_cron = True
                return False
            else:
                raise Warning(_(message_body))

        currency_id = journal.currency_id.id or self.instance_id.shopify_company_id.currency_id.id or False
        if currency_id != self.currency_id.id:
            message_body = "Report currency and Currency in Instance Journal are different.\nMake sure Report currency and Instance Journal currency must be same."
            self.message_post(body=_(message_body))

        bank_statement_exist = bank_statement_obj.search([('shopify_payout_ref', '=', self.payout_reference_id)], limit=1)

        if bank_statement_exist:
            self.write({'statement_id': bank_statement_exist.id})
            self.is_skip_from_cron = False
            return True

        name = '{0}_{1}'.format(self.instance_id.name, self.payout_reference_id)
        vals = {
            'shopify_payout_ref': self.payout_reference_id,
            'journal_id': journal.id,
            'name': name,
            'accounting_date': self.payout_date,
	        'date' : self.payout_date,
        }
        bank_statement_id = bank_statement_obj.create(vals)
        for transaction in self.payout_transaction_ids:
            order_id = transaction.order_id
            if transaction.transaction_type in ['charge', 'refund'] and not order_id:
                message = "Transaction line is skip due to order {0} is not found in odoo.".format(
                    transaction.source_order_id)
                payout_logline_obj.create({'message': message,
                                           'instance_id': self.instance_id.id,
                                           'payout_transaction_ref': transaction.transaction_id,
                                           'payout_id': self.id})
                transaction.is_remaining_statement = True
                continue
            partner = partner_obj._find_accounting_partner(order_id.partner_id)
            invoice_ids = account_invoice_obj
            account_id = False
            if transaction.transaction_type == 'charge':
                invoice_ids = order_id.invoice_ids.filtered(lambda l: l.state == 'posted' and l.type == 'out_invoice' and l.amount_total == transaction.amount)
                if not invoice_ids:
                    message = "Invoice is not created for order %s in odoo" % (order_id.name or transaction.source_order_id)
                    payout_logline_obj.create({'message': message,
                                               'is_skipped': True,
                                               'instance_id': self.instance_id.id,
                                               'payout_transaction_ref': transaction.transaction_id,
                                               'payout_id': self.id})
                    transaction.is_remaining_statement = True
                    continue
            if transaction.transaction_type == 'refund':
                invoice_ids = order_id.invoice_ids.filtered(lambda l: l.state == 'posted' and l.type == 'out_refund' and l.amount_total == -(transaction.amount))
                if not invoice_ids:
                    message = "In shopify payout there is refund, but Refund is not created for order %s in odoo" % (order_id.name or transaction.source_order_id)
                    payout_logline_obj.create({'message': message,
                                               'is_skipped': True,
                                               'instance_id': self.instance_id.id,
                                               'payout_transaction_ref': transaction.transaction_id,
                                               'payout_id': self.id})
                    transaction.is_remaining_statement = True
                    continue

            payment_reference = False
            if transaction.transaction_type not in ['charge', 'refund']:
                shopify_account_config_id = self.instance_id.transaction_line_ids.filtered(lambda l:
                                                                                           l.transaction_type ==
                                                                                           transaction.transaction_type)
                account_id = shopify_account_config_id and shopify_account_config_id.account_id
            if transaction.transaction_type == 'charge':
                payment_reference = self.env['account.payment'].search([('invoice_ids', 'in',invoice_ids.ids),
                                                                        ('amount', '=', transaction.amount),
                                                                        ('payment_type', '=','inbound')], limit=1)
            if transaction.transaction_type == 'refund':
                payment_reference = self.env['account.payment'].search([('invoice_ids', 'in',invoice_ids.ids),
                                                                        ('amount', '=',-(transaction.amount)),
                                                                        ('payment_type', '=','outbound')], limit=1)
            if payment_reference:
                reference = payment_reference.name
                payment_aml_rec = payment_reference.mapped('move_line_ids').filtered(lambda line: line.account_internal_type == "liquidity")
                if self.check_reconciled_transactions(transaction, payment_aml_rec):
                    continue
            else:
                reference = invoice_ids.name or ''

            if transaction.amount:
                bank_line_vals = {
                    'name': order_id.name or transaction.transaction_type,
                    'ref': reference or '',
                    'date': self.payout_date,
                    'partner_id': partner and partner.id,
                    'amount': transaction.amount,
                    'statement_id': bank_statement_id.id,
                    'shopify_order_ids': [(6, 0, order_id.ids)],
                    'shopify_transaction_id': transaction.transaction_id,
                    'shopify_transaction_type': transaction.transaction_type,
                }
                if account_id:
                    bank_line_vals.update({'account_ept_id': account_id.id})
                bank_statement_line_obj.create(bank_line_vals)

        if self.check_process_statement():
            state = 'generated'
        else:
            state = 'partially_generated'

        if bank_statement_id:
            self.write({'statement_id': bank_statement_id.id, 'state': state})
        if self.reconciliation_log_ids:
            self.env['shopify.payout.logline.ept'].create_payout_schedule_activity(self.reconciliation_log_ids)
        self.is_skip_from_cron = False
        return True

    def check_reconciled_transactions(self, transaction, aml_rec=False):
        payout_logline_obj = self.env['shopify.payout.logline.ept']
        reconciled = False
        if aml_rec and aml_rec.statement_id:
            message = 'Transaction line is already reconciled.'
            payout_logline_obj.create({'message': message,
                                       'is_skipped': False,
                                       'instance_id': self.instance_id.id,
                                       'payout_transaction_ref': transaction.transaction_id,
                                       'payout_id': self.id})
            reconciled = True
        return reconciled

    def convert_move_amount_currency(self, bank_statement, moveline, amount):
        amount_currency = 0.0
        if moveline.company_id.currency_id.id != bank_statement.currency_id.id:
            # In the specific case where the company currency and the statement currency are the same
            # the debit/credit field already contains the amount in the right currency.
            # We therefore avoid to re-convert the amount in the currency, to prevent Gain/loss exchanges
            amount_currency = moveline.currency_id.compute(moveline.amount_currency,bank_statement.currency_id)
        elif (moveline.move_id and moveline.move_id.currency_id.id != bank_statement.currency_id.id):
            amount_currency = moveline.move_id.currency_id.compute(amount,bank_statement.currency_id)
        currency = moveline.currency_id.id
        return currency, amount_currency

    def process_bank_statement(self):
        statement_line_obj = self.env['account.bank.statement.line']
        payout_logline_obj = self.env['shopify.payout.logline.ept']
        move_line_obj = self.env['account.move.line']
        invoice_obj = self.env['account.move']
        account_payment_obj = self.env['account.payment']
        bank_statement = self.statement_id
        _logger.info("Processing Bank Statement: {0}.".format(bank_statement.name))
        for statement_line in bank_statement.line_ids.filtered(lambda x: x.journal_entry_ids.ids == []):
            try:
                mv_list = []
                payment_aml_rec = []
                mv_line_dicts = []
                ref = statement_line.ref
                if ref:
                    payment_id = account_payment_obj.search([('name', '=', ref)], limit=1)
                    if payment_id:
                        payment_aml_rec = payment_id.mapped('move_line_ids').filtered(lambda line:line.account_internal_type == "liquidity")
                else:
                    if statement_line.account_ept_id:
                        mv_dicts = {
                            'account_id': statement_line.account_ept_id.id,
                            'debit': statement_line.amount < 0 and -statement_line.amount or 0.0,
                            'credit': statement_line.amount > 0 and statement_line.amount or 0.0,
                        }
                        if statement_line.amount < 0.0:
                            mv_dicts.update({'debit': -statement_line.amount})
                        else:
                            mv_dicts.update({'credit': statement_line.amount})
                        mv_list.append(mv_dicts)
                invoices = invoice_obj.browse()
                if not payment_aml_rec and not mv_list:
                    for order in statement_line.shopify_order_ids:
                        if statement_line.amount < 0.0:
                            invoices += order.invoice_ids.filtered(lambda record: record.type == 'out_refund' and record.state == 'posted')
                        else:
                            invoices += order.invoice_ids.filtered(lambda record: record.type == 'out_invoice' and record.state == 'posted')
                    for invoice in invoices:
                        if invoice.state == 'posted':
                            payment_ids = account_payment_obj.search([('invoice_ids','in',invoice.ids)])
                            if payment_ids:
                                payment_aml_rec = payment_ids.mapped('move_line_ids').filtered(lambda line: line.user_type_id.type == "liquidity")
                            else:
                                move_lines = invoices.mapped('line_ids').filtered(lambda l: l.account_id.user_type_id.type == 'receivable' and not l.reconciled)
                                move_line_total_amount = 0.0
                                currency_ids = []
                                for moveline in move_lines:
                                    amount = moveline.debit - moveline.credit
                                    amount_currency = 0.0
                                    if moveline.amount_currency:
                                        currency, amount_currency = self.convert_move_amount_currency(bank_statement, moveline, amount)
                                        if currency:
                                            currency_ids.append(currency)
                                    if amount_currency:
                                        amount = amount_currency
                                    mv_line_dicts.append({
                                        'credit': abs(amount) if amount > 0.0 else 0.0,
                                        'name': moveline.move_id.name,
                                        'move_line': moveline,
                                        'debit': abs(amount) if amount < 0.0 else 0.0
                                    })
                                    move_line_total_amount += amount

                                if round(statement_line.amount, 10) == round(move_line_total_amount, 10) and (
                                        not statement_line.currency_id or statement_line.currency_id.id == bank_statement.currency_id.id):
                                    if currency_ids:
                                        currency_ids = list(set(currency_ids))
                                        if len(currency_ids) == 1:
                                            statement_line.write({'amount_currency': move_line_total_amount,
                                                                  'currency_id': currency_ids[0]})
                    already_reconciled = False
                    for aml_dict in mv_line_dicts:
                        if aml_dict['move_line'].reconciled:
                            message = "Bank statement line unlink due to transaction has already reconciled."
                            _logger.info("Statement line is already reconciled: {0}".format(
                                statement_line.ref or statement_line.name or ''))
                            already_reconciled = True
                    if any(rec.statement_id for rec in payment_aml_rec):
                        message = "Bank statement line unlink due to transaction has already reconciled."
                        _logger.info("Statement line is already reconciled: {0}".format(
                            statement_line.ref or statement_line.name or ''))
                        already_reconciled = True

                    if already_reconciled:
                        payout_logline_obj.create({'message': message,
                                                   'instance_id': self.instance_id.id,
                                                   'payout_transaction_ref': statement_line.shopify_transaction_id,
                                                   'payout_id': self.id})
                        continue

                statement_line.process_reconciliation(counterpart_aml_dicts=mv_line_dicts,
                                                      payment_aml_rec=payment_aml_rec, new_aml_dicts=mv_list)
                _logger.info(
                    "Statement reconciled for Reference: {0}, Label: {1}, Amount: {2}.".format(statement_line.ref or '',
                                                                                               statement_line.name or '',
                                                                                               statement_line.amount))
            except Exception as error:
                message = "statement line occurred while reconciliation : {0}.".format(error)
                payout_logline_obj.create({'message': message,
                                           'instance_id': self.instance_id.id,
                                           'payout_transaction_ref': statement_line.shopify_transaction_id,
                                           'payout_id': self.id})
        if statement_line_obj.search([('journal_entry_ids', '=', False),('statement_id', '=', bank_statement.id)]):
            self.write({'state': 'partially_processed'})
        else:
            self.write({'state': 'processed'})

        return True

    def get_payout_report(self, start_date, end_date, instance):
        """
        Use : Using this method get Payout records as per date given.
        Added by : Deval Jagad (02/06/2020)
        Task ID : 164126
        :param start_date:From Date(year-month-day)
        :param end_date: To Date(year-month-day)
        :param instance: Browsable shopify instance.
        :return: True
        """
        shopify_payout_report_line_obj = self.env['shopify.payout.report.line.ept']
        log_book_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']
        log_book_id = False
        if not instance.shopify_api_url:
            raise Warning(_("Shopify API URL is blank!"))

        shop = instance.shopify_host.split("//")
        headers = {"Accept": "application/json",
                   "Content-Type": "application/json; charset=utf-8"}
        params = {"status": 'paid', "date_min": start_date, "date_max": end_date, "limit": 250}
        try:
            shopify_api_url = instance.shopify_api_url + 'payouts.json'
            payout_ids = []
            if len(shop) == 2:
                url = "{0}//{1}:{2}@{3}/{4}".format(shop[0], instance.shopify_api_key, instance.shopify_password,shop[1], shopify_api_url)
            else:
                url = "https://{0}:{1}@{2}/{3}".format(instance.shopify_api_key, instance.shopify_password,shop[0],shopify_api_url)
            response = requests.get(url, params=params, headers=headers)
            payout_response = response.json()
            payout_ids = payout_ids + payout_response.get('payouts', [])
        except Exception as error:
            message = "Something is wrong while import the payout records : {0}".format(error)
            if not log_book_id:
                model = "shopify.payout.report.ept"
                model_id = self.env["common.log.lines.ept"].get_model_id(model)
                log_book_id = log_book_obj.create({'type': 'import',
                                                   'module': 'shopify_ept',
                                                   'shopify_instance_id': instance.id,
                                                   'model_id':model_id and model_id.id,
                                                   'create_date':datetime.now(),
                                                   'active': True})
            log_line_obj.create({'log_line_id':log_book_id,
                                 'message':message,
                                 'model_id':model_id and model_id.id or False,
                                 })
            return False

        for payout in payout_ids:
            _logger.info("Payout ID %s ", payout.get('id'))
            payout_id = self.search([('instance_id', '=', instance.id),
                                     ('payout_reference_id', '=', payout.get('id'))])
            if payout_id:
                continue
            payout_vals = self.prepare_payout_vals(payout, instance)
            payout_id = self.create(payout_vals)

            if not payout_id:
                continue
            # Get Payout Transaction data and Create record.
            transaction_ids = self.get_payout_transactions_data(payout_id, instance)
            for transaction in transaction_ids:
                _logger.info("Transaction ID %s ", transaction.get('id'))
                transaction_vals = self.prepare_transaction_vals(transaction, payout_id,
                                                                 instance)
                shopify_payout_report_line_obj.create(transaction_vals)
            # Create fees line
            fees_amount = float(payout.get('summary').get('charges_fee_amount', 0.0)) + float(
                    payout.get('summary').get('refunds_fee_amount', 0.0)) + float(
                    payout.get('summary').get('adjustments_fee_amount', 0.0))
            shopify_payout_report_line_obj.create({
                'payout_id': payout_id.id or False,
                'transaction_id': '',
                'source_order_id': '',
                'transaction_type': 'fees',
                'order_id': '',
                'amount': -fees_amount,
                'fee': 0.0,
                'net_amount': fees_amount,
            })
        instance.write({'payout_last_import_date': datetime.now()})
        return True

    def prepare_transaction_vals(self, data, payout_id, instance):
        """
        Use : Based on transaction data prepare transaction vals.
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        :param data: Tramsaction data in dict{}.
        :param payout_id: Browsable reocord of payout_id.
        :param instance: Browsable reocord of instance.
        :return: Payout vals{}
        """
        currency_obj = self.env['res.currency']
        sale_order_obj = self.env['sale.order']
        transaction_id = data.get('id', '')
        source_order_id = data.get('source_order_id', '')
        transaction_type = data.get('type', '')
        amount = data.get('amount', 0.0)
        fee = data.get('fee', 0.0)
        net_amount = data.get('net', 0.0)
        currency = data.get('currency', '')

        order_id = False
        if source_order_id:
            order_id = sale_order_obj.search([('shopify_order_id', '=', source_order_id),
                                              ('shopify_instance_id', '=', instance.id)],
                                             limit=1)

        transaction_vals = {
            'payout_id': payout_id.id or False,
            'transaction_id': transaction_id,
            'source_order_id': source_order_id,
            'transaction_type': transaction_type,
            'order_id': order_id and order_id.id,
            'amount': amount,
            'fee': fee,
            'net_amount': net_amount,
        }

        currency_id = currency_obj.search([('name', '=', currency)], limit=1)
        if currency_id:
            transaction_vals.update({'currency_id': currency_id.id})

        return transaction_vals

    def prepare_payout_vals(self, data, instance):
        """
        Use : Based on payout data prepare payout vals.
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        :param data: Payout data in dict{}.
        :param instance: Browsable reocord of instance.
        :return: Payout vals{}
        """
        currency_obj = self.env['res.currency']
        payout_reference_id = data.get('id')
        payout_date = data.get('date', '')
        payout_status = data.get('status', '')
        currency = data.get('currency', '')
        amount = data.get('amount', 0.0)

        payout_vals = {
            'payout_reference_id': payout_reference_id,
            'payout_date': payout_date,
            'payout_status': payout_status,
            'amount': amount,
            'instance_id': instance.id
        }
        currency_id = currency_obj.search([('name', '=', currency)], limit=1)
        if currency_id:
            payout_vals.update({'currency_id': currency_id.id})
        return payout_vals

    def get_payout_transactions_data(self, payout_id, instance):
        """
        Use : Based on payout id get transaction data.
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        :param payout_id:
        :param instance:
        :return:
        """
        shop = instance.shopify_host.split("//")
        headers = {"Accept": "application/json",
                   "Content-Type": "application/json; charset=utf-8"}
        params = {'payout_id': payout_id.payout_reference_id, "limit": 250}
        shopify_api_url = instance.shopify_api_url + 'balance/transactions.json'
        transaction_ids = []
        if len(shop) == 2:
            url = "{0}//{1}:{2}@{3}/{4}".format(shop[0], instance.shopify_api_key, instance.shopify_password,
                                                shop[1], shopify_api_url)
        else:
            url = "https://{0}:{1}@{2}/{3}".format(instance.shopify_api_key, instance.shopify_password,
                                                   shop[0],
                                                   shopify_api_url)
        response = requests.get(url, params=params, headers=headers)
        if response.status_code not in [200, 201]:
            return True
        try:
            transaction_response = response.json()
        except Exception as error:
            raise Warning(error)
        transaction_ids = transaction_ids + transaction_response.get('transactions', [])
        return transaction_ids

    def closed_statement(self):
        """
        Use : To reconcile the bank statement
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        :return: True
        """
        payout_logline_obj = self.env['shopify.payout.logline.ept']
        try:
            self.statement_id.button_confirm_bank()
        except Exception as e:
            message_body = "There is some issue in close statement: Error: {0} ".format(e)
            log_line_id = payout_logline_obj.search([('payout_id','=',self.id),
                                                     ('instance_id','=',self.instance_id.id),
                                                     ('message','=',message_body)])
            if not log_line_id:
                log_line_id = payout_logline_obj.create({'message': message_body,
                                                         'instance_id': self.instance_id.id,
                                                         'payout_id': self.id})
            self.env['shopify.payout.logline.ept'].with_context({'is_closed':True}).create_payout_schedule_activity(log_line_id)
            self.is_skip_from_cron = True
            return False
        self.state = 'closed'
        return True

    def unlink(self):
        """
        Use : Inherite method for Raiser warning if it is in Processed or closed state.
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        :return: Raise warning of call super method.
        """
        for report in self:
            if report.state != 'draft':
                raise Warning(_('You cannot delete payout report.'))
        return super(ShopifyPaymentReportEpt, self).unlink()

    def create(self, vals):
        """
        Use : Inherite Create method to Create Unique sequence for import payout.
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        :param vals: dictionary
        :return: result
        """
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'import.payout.report.ept') or _('New')
        result = super(ShopifyPaymentReportEpt, self).create(vals)
        return result


    def auto_import_payout_report(self, ctx={}):
        """
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        Func: this method use get payout report from the last import payout date and current date
        :param ctx: use for the instance
        :return: True
        """
        shopify_instance_obj = self.env['shopify.instance.ept']
        payout_report_obj = self.env['shopify.payout.report.ept']
        if not isinstance(ctx, dict) or not 'shopify_instance_id' in ctx:
            return True
        shopify_instance_id = ctx.get('shopify_instance_id', False)
        if shopify_instance_id:
            instance = shopify_instance_obj.search([('id', '=', shopify_instance_id)])
            if instance.payout_last_import_date:
                _logger.info("cron =====:Auto Import Payout Report =====")
                payout_report_obj.get_payout_report(start_date=instance.payout_last_import_date,
                                                    end_date=datetime.now(), instance=instance)
            return True

    def auto_generate_bank_statement(self, ctx={}):
        """
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        Func: this method use for search  draft report and then generate  bank statement
        :param ctx: use for the instance
        :return: True
        """
        shopify_instance_obj = self.env['shopify.instance.ept']
        if not isinstance(ctx, dict) or not 'shopify_instance_id' in ctx:
            return True
        shopify_instance_id = ctx.get('shopify_instance_id', False)
        if shopify_instance_id:
            instance = shopify_instance_obj.search([('id', '=', shopify_instance_id)])
            payout_report_obj = self.env['shopify.payout.report.ept']
            draft_reports = payout_report_obj.search(
                [('state', '=', 'draft'), ('instance_id', '=', instance.id), ('is_skip_from_cron', '!=', True)])
            for draft_report in draft_reports:
                _logger.info("cron =====:Auto Generate Bank Statement: {0} =====".format(draft_report.name))
                draft_report.with_context({'is_cron':True}).generate_bank_statement()
            partially_generated_report = payout_report_obj.search(
                    [('state', '=', 'partially_generated'), ('instance_id', '=', instance.id), ('is_skip_from_cron', '!=', True)])
            for report in partially_generated_report:
                _logger.info("Cron : +++ Partially processed report : {0}".format(report.name))
                report.generate_remaining_bank_statement()
        return True

    def auto_process_bank_statement(self, ctx={}):
        """
        Added by : Deval Jagad
        Added on : 05/06/2020
        Task ID : 164126
        Func: this method use for search  generated report and then process bank statement
        :param ctx: use for the instance
        :return: True
        """
        shopify_instance_obj = self.env['shopify.instance.ept']
        if not isinstance(ctx, dict) or not 'shopify_instance_id' in ctx:
            return True
        shopify_instance_id = ctx.get('shopify_instance_id', False)
        if shopify_instance_id:
            instance = shopify_instance_obj.search([('id', '=', shopify_instance_id)])
            payout_report_obj = self.env['shopify.payout.report.ept']
            generated_reports = payout_report_obj.search(
                [('state', '=', 'generated'), ('instance_id', '=', instance.id),
                 ('is_skip_from_cron', '!=', True)],order="payout_date asc")
            for generated_report in generated_reports:
                _logger.info("cron =====:Auto Process Bank Statement: {0} =====".format(generated_report.name))
                generated_report.process_bank_statement()
            processed_reports = payout_report_obj.search(
                    [('state', '=', 'processed'), ('instance_id', '=', instance.id), ('is_skip_from_cron', '!=', True)])
            for processed_report in processed_reports:
                processed_report.closed_statement()
        return True
