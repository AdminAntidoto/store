from odoo import models


class DataQueueMixinEpt(models.AbstractModel):
    """ Mixin class for delete unused data queue from database."""
    _name = 'data.queue.mixin.ept'
    _description = 'Data Queue Mixin'

    def delete_data_queue_ept(self, queue_detail=[]):
        """
        Method for Delete unused data queues from connectors.
        @author: Keyur Kanani
        :param queue_detail: [{'table': 'sample_data_queue_ept', 'state': ('done','completed'), 'days': int}]
        :return: True
        """
        if queue_detail:
            try:
                for tbl_name in queue_detail:
                    table = tbl_name.get('table', '')
                    state = tbl_name.get('state', '')
                    days = tbl_name.get('days', '')
                    if table and state and days:
                        state = ''.join("('{}')".format(state)) if type(state) == str else state
                        self._cr.execute(
                            """delete from %s where state in %s and cast(create_date as Date) <= current_date - %d""" % (
                                table, state, int(days)))
            except Exception as e:
                return e
        return True
