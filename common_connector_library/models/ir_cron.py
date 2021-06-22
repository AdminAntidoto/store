from odoo import models
from datetime import datetime


class IrCron(models.Model):
    _inherit = "ir.cron"

    def try_cron_lock(self):
        """
        To check scheduler status is running or when nextcall from cron id.
        :return:
        """
        try:
            self._cr.execute("""SELECT id FROM "%s" WHERE id IN %%s FOR UPDATE NOWAIT""" % self._table,
                             [tuple(self.ids)], log_exceptions=False)
            difference = self.nextcall - datetime.now()
            if not difference.days < 0:
                days = difference.days * 1440 if difference.days > 0 else 0
                minutes = int(difference.seconds / 60) + days
                return {"result": minutes}
        except:
            return {
                "reason": "This cron task is currently being executed, If you execute this action it may cause duplicate records"}
