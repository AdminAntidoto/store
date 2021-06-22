{
    # App information
    'name': 'Shopify Odoo Connector',
    'version': '13.0.30',
    'category': 'Sales',
    'summary': 'Shopify Odoo Connector helps you in integrating and managing your Shopify store with Odoo by providing the most useful features of Product and Order Synchronization.',
    'license': 'OPL-1',

    # Author
    'author': 'Emipro Technologies Pvt. Ltd.',
    'website': 'http://www.emiprotechnologies.com/',
    'maintainer': 'Emipro Technologies Pvt. Ltd.',

    # Dependencies
    'depends': ['common_connector_library',
                'auto_invoice_workflow_ept'],

    # Views
    'init_xml': [],
    'data': [
        'security/group.xml',
        'security/ir.model.access.csv',
        'view/instance_view.xml',
        'wizard/res_config_view.xml',
        'data/ir_sequence.xml',
        'data/ir_cron_data.xml',
        'data/product_data.xml',
        'data/import_order_status.xml',
        'view/common_log_book_view.xml',
        'view/shopify_job_log.xml',
        'view/product_template_view.xml',
        'view/product_product_view.xml',
        'wizard/process_import_export_view.xml',
        'view/customer_data_queue_line_ept.xml',
        'view/payment_gateway_view.xml',
        'wizard/queue_process_wizard_view.xml',
        'view/product_data_queue_view.xml',
        'view/order_data_queue_ept.xml',
        'view/customer_data_queue_ept.xml',
        'view/location_ept.xml',
        'view/sale_order_view.xml',
        'view/res_partner_view.xml',
        'view/sale_workflow_config_view.xml',
        'view/stock_picking_view.xml',
        'wizard/cron_configuration_ept.xml',
        'wizard/cancel_refund_order_wizard_view.xml',
        'view/account_invoice_view.xml',
        'report/sale_report_view.xml',
        'view/dashboard_view.xml',
        'view/order_data_queue_line_ept.xml',
        'view/product_data_queue_line_view.xml',
        'view/product_image_ept.xml',
        "wizard/prepare_product_for_export.xml",
        'view/shopify_payout_report_ept.xml',
    ],
    'demo_xml': [],

    # Odoo Store Specific
    'images': ['static/description/shopify-odoo-cover.gif'],

    'installable': True,
    'auto_install': False,
    'application': True,
    'live_test_url': 'https://www.emiprotechnologies.com/free-trial?app=shopify-ept&version=13&edition=enterprise',
    'price': 379.00,
    'currency': 'EUR',
    }
