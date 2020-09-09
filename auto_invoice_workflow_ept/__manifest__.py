{
    # App information
    'name': 'Automatic Workflow Settings',
    'version': '13.0.4',
    'category': 'Sale',
    'license': 'OPL-1',
    # Author
    'author': 'Emipro Technologies Pvt. Ltd.',
    'website': 'http://www.emiprotechnologies.com',
    'maintainer': 'Emipro Technologies Pvt. Ltd.',
    # Dependencies
    'depends': ['sale_management', 'stock'],
    'data':['view/sale_workflow_process_view.xml',
            'view/automatic_workflow_data.xml',
            'view/sale_view.xml',
            'security/ir.model.access.csv'],
    'installable': True,
    'images': ['static/description/Automatic-Workflow-Cover.jpg'],
    'price': 0.00,
    'currency': 'EUR',
}
