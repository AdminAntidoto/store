from odoo import models, fields

class SaleAutoWorkflowConfiguration(models.Model):
    _name = "sale.auto.workflow.configuration.ept"
    _description = 'Sale auto workflow configuration'

    financial_status = fields.Selection([('pending', 'The finances are pending'),
                                         ('authorized', 'The finances have been authorized'),
                                         (
                                         'partially_paid', 'The finances have been partially paid'),
                                         ('paid', 'The finances have been paid'),
                                         ('partially_refunded',
                                          'The finances have been partially refunded'),
                                         ('refunded', 'The finances have been refunded'),
                                         ('voided', 'The finances have been voided')
                                         ], default="paid", required=1)
    auto_workflow_id = fields.Many2one("sale.workflow.process.ept", "Auto Workflow", required=1)
    payment_gateway_id = fields.Many2one("shopify.payment.gateway.ept", "Payment Gateway",
                                         required=1)
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term', required=1)
    shopify_instance_id = fields.Many2one("shopify.instance.ept", "Instance", required=1)
    _sql_constraints = [('_workflow_unique_constraint',
                         'unique(financial_status,shopify_instance_id,payment_gateway_id)',
                         "Financial status must be unique in the list")]

