from csv import DictWriter

"""
Method Return :- Create CSV File
Pass Parameter :-
1) datas = List Of Dictionary
2)field_name = list of filed_name
3)delimiter

add import statement in which place call the Method
from odoo.addons.common_connector_library.api.csv_reader_writer import csv_writer

In this way Method Call :- csv_writer(list_item,field_name,';')
"""


class csv_writer():

    def __init__(self, datas, field_name, delimiter='\t'):
        with open('/tmp/record.csv', 'w') as file:
            csvwriter = DictWriter(file, field_name, delimiter)
            csvwriter.writeheader()
            csvwriter.writerows(datas)
            file.close()


#         file = StringIO()
#         csvwriter = DictWriter(file, field_name,delimiter=';')
#         csvwriter.writer.writerow(field_name)
#         for data in datas:
#             csvwriter.writerow(data)
#         file.close()
"""
Method Return :- List Of Dictionary

add import statement in which place call the Method
from odoo.addons.common_connector_library.api.csv_reader_writer import csv_reader_ept 

In this way call the Method :- csv_reader_ept.read_file(self,filepath)

"""


class csv_reader_ept():

    def read_file(self, filename):
        list_record = []
        with open(filename) as myfile:
            firstline = True
            for line in myfile:
                if firstline:
                    mykeys = "".join(line.split()).split(',')
                    firstline = False
                else:
                    values = "".join(line.split()).split(',')
                    list_record.append({mykeys[n]: values[n] for n in range(0, len(mykeys))})
        return list_record
