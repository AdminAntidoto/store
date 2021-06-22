# !/usr/bin/python3
# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    #Shopify Payout Report
    shopify_payout_ref = fields.Char(string='Shopify Payout Reference')


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    #Shopify Payout Report
    shopify_transaction_id = fields.Char("Shopify Transaction")
    shopify_order_ids = fields.Many2many("sale.order", "statement_order_shopify_rel", "line_id",
                                         "order_id")
    # shopify_refund_invoice_ids = fields.Many2many('account.invoice',
    #                                               'statement_refund_invoice_shopify_ref',
    #                                               'line_id', 'invoice_id')
    account_ept_id = fields.Many2one('account.account')
    shopify_transaction_type = fields.Selection(
        [('charge', 'Charge'), ('refund', 'Refund'), ('dispute', 'Dispute'),
         ('reserve', 'Reserve'), ('adjustment', 'Adjustment'), ('credit', 'Credit'),
         ('debit', 'Debit'), ('payout', 'Payout'), ('payout_failure', 'Payout Failure'),
         ('payout_cancellation', 'Payout Cancellation'), ('fees', 'Fees')],
        help="The type of the balance transaction", string="Balance Transaction Type")
