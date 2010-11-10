# Copyright (C) 2007-2010 Samuel Abels.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""
Represents a call to a service.
"""
import os, traceback, shutil
import Exscript
from datetime           import datetime
from Exscript.util.file import get_hosts_from_csv
from tempfile           import NamedTemporaryFile
from lxml               import etree
from DBObject           import DBObject

class Order(DBObject):
    """
    An order includes all information that is required to make a
    service call.
    """

    def __init__(self, service_name):
        """
        Constructor. The service_name defines the service to whom
        the order is delivered. In other words, this is the
        service name is assigned in the config file of the server.

        @type  service_name: str
        @param service_name: The service that handles the order.
        """
        self.id         = None
        self.status     = 'new'
        self.service    = service_name
        self.hosts      = []
        self.descr      = ''
        self.created    = datetime.utcnow()
        self.closed     = None
        self.created_by = os.environ.get('USER')

    def __repr__(self):
        return "<Order('%s','%s','%s')>" % (self.id, self.service, self.status)

    @staticmethod
    def from_etree(order_node):
        """
        Creates a new instance by parsing the given XML.

        @type  order_node: lxml.etree.Element
        @param order_node: The order node of an etree.
        @rtype:  Order
        @return: A new instance of an order.
        """
        # Parse required attributes.
        descr_node       = order_node.find('description')
        order            = Order(order_node.get('service'))
        order.id         = order_node.get('id')
        order.status     = order_node.get('status',     order.status)
        order.created_by = order_node.get('created-by', order.created_by)
        created          = order_node.get('created')
        closed           = order_node.get('closed')
        if descr_node is not None:
            order.descr = descr_node.text
        if created:
            created = created.split('.', 1)[0]
            created = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
            order.created = created
        if closed:
            closed = closed.split('.', 1)[0]
            closed = datetime.strptime(closed, "%Y-%m-%d %H:%M:%S")
            order.closed = closed
        order._read_hosts_from_xml(order_node)
        return order

    @staticmethod
    def from_xml(xml):
        """
        Creates a new instance by parsing the given XML.

        @type  xml: str
        @param xml: A string containing an XML formatted order.
        @rtype:  Order
        @return: A new instance of an order.
        """
        xml = etree.fromstring(xml)
        return Order.from_etree(xml.find('order'))

    @staticmethod
    def from_xml_file(filename):
        """
        Creates a new instance by reading the given XML file.

        @type  filename: str
        @param filename: A file containing an XML formatted order.
        @rtype:  Order
        @return: A new instance of an order.
        """
        # Parse required attributes.
        xml = etree.parse(filename)
        return Order.from_etree(xml.find('order'))

    @staticmethod
    def from_csv_file(service, filename, encoding = 'utf-8'):
        """
        Creates a new instance by reading the given CSV file.

        @type  service: str
        @param service: The service name.
        @type  filename: str
        @param filename: A file containing a CSV formatted list of hosts.
        @type  encoding: str
        @param encoding: The name of the encoding.
        @rtype:  Order
        @return: A new instance of an order.
        """
        order = Order(service)
        order.add_hosts_from_csv(filename, encoding = encoding)
        return order

    def _read_list_from_xml(self, list_elem):
        items = list_elem.iterfind('list-item')
        if items is None:
            return []
        return [i.text.strip() for i in items if i.text is not None]

    def _read_arguments_from_xml(self, host_elem):
        arg_elem = host_elem.find('argument-list')
        if arg_elem is None:
            return {}
        args = {}
        for child in arg_elem:
            name = child.get('name').strip()
            if child.tag == 'variable':
                args[name] = child.text.strip()
            elif child.tag == 'list':
                args[name] = self._read_list_from_xml(child)
            else:
                raise Exception('Invalid XML tag: %s' % element.tag)
        return args

    def _read_hosts_from_xml(self, element):
        for host_elem in element.iterfind('host'):
            name    = host_elem.get('name', '').strip()
            address = host_elem.get('address', name).strip()
            args    = self._read_arguments_from_xml(host_elem)
            host    = Exscript.Host(address)
            if not address:
                raise TypeError('host element without name or address')
            if name:
                host.set_name(name)
            host.set_all(args)
            self.add_host(host)

    def _list_to_xml(self, root, name, thelist):
        list_elem = etree.SubElement(root, 'list', name = name)
        for value in thelist:
            item = etree.SubElement(list_elem, 'list-item')
            item.text = value
        return list_elem

    def _arguments_to_xml(self, root, args):
        arg_elem = etree.SubElement(root, 'argument-list')
        for name, value in args.iteritems():
            if isinstance(value, list):
                self._list_to_xml(arg_elem, name, value)
            elif isinstance(value, str):
                variable = etree.SubElement(arg_elem, 'variable', name = name)
                variable.text = value
            else:
                raise Exception('unknown variable type')
        return arg_elem

    def toetree(self):
        """
        Returns the order as an lxml etree.

        @rtype:  lxml.etree
        @return: The resulting tree.
        """
        order = etree.Element('order', service = self.service)
        if self.id:
            order.attrib['id'] = str(self.id)
        if self.status:
            order.attrib['status'] = str(self.status)
        if self.created:
            order.attrib['created'] = str(self.created)
        if self.closed:
            order.attrib['closed'] = str(self.closed)
        if self.descr:
            etree.SubElement(order, 'description').text = str(self.descr)
        if self.created_by:
            order.attrib['created-by'] = str(self.created_by)
        for host in self.hosts:
            elem = etree.SubElement(order,
                                    'host',
                                    address = host.get_address(),
                                    name    = host.get_name())
            self._arguments_to_xml(elem, host.get_all())
        return order

    def toxml(self, pretty = True):
        """
        Returns the order as an XML formatted string.

        @type  pretty: bool
        @param pretty: Whether to format the XML in a human readable way.
        @rtype:  str
        @return: The XML representing the order.
        """
        xml   = etree.Element('xml')
        order = self.toetree()
        xml.append(order)
        return etree.tostring(xml, pretty_print = pretty)

    def write(self, filename):
        """
        Export the order as an XML file.

        @type  filename: str
        @param filename: XML
        """
        dirname  = os.path.dirname(filename)
        file     = NamedTemporaryFile(dir = dirname, prefix = '.') #delete = False)
        file.write(self.toxml())
        file.flush()
        os.chmod(file.name, 0644)
        os.rename(file.name, filename)
        try:
            file.close()
        except:
            pass

    def is_valid(self):
        """
        Returns True if the order validates, False otherwise.

        @rtype:  bool
        @return: True if the order is valid, False otherwise.
        """
        return True #FIXME

    def get_id(self):
        """
        Returns the order id.

        @rtype:  str
        @return: The id of the order.
        """
        return self.id

    def set_service_name(self, name):
        """
        Set the name of the service that is ordered.

        @type  name: str
        @param name: The service name.
        """
        self.service = name

    def get_service_name(self):
        """
        Returns the name of the service that is ordered.

        @rtype:  str
        @return: The service name.
        """
        return self.service

    def get_status(self):
        """
        Returns the order status.

        @rtype:  str
        @return: The order status.
        """
        return self.status

    def set_description(self, description):
        """
        Sets a freely defined description on the order.

        @type  description: str
        @param description: The new description.
        """
        self.descr = description and str(description) or ''

    def get_description(self):
        """
        Returns the description of the order.

        @rtype:  str
        @return: The description.
        """
        return self.descr

    def get_created_timestamp(self):
        """
        Returns the time at which the order was created.

        @rtype:  datetime.datetime
        @return: The timestamp.
        """
        return self.created

    def get_closed_timestamp(self):
        """
        Returns the time at which the order was closed, or None if the
        order is still open.

        @rtype:  datetime.datetime|None
        @return: The timestamp or None.
        """
        return self.closed

    def get_created_by(self):
        """
        Returns the username of the user who opened the order. Defaults
        to the USER environment variable.

        @rtype:  str
        @return: The value of the 'created-by' field.
        """
        return self.created_by

    def close(self):
        """
        Marks the order closed.
        """
        self.closed = datetime.utcnow()

    def add_host(self, host):
        """
        Adds the given host to the order.

        @type  host: Exscript.Host
        @param host: A host object.
        """
        self.touch()
        self.hosts.append(DBObject(host))

    def add_hosts_from_csv(self, filename, encoding = 'utf-8'):
        """
        Parses the given CSV file using
        Exscript.util.file.get_hosts_from_csv(), and adds the resulting
        Exscript.Host objects to the order.
        Multi-column CSVs are supported, i.e. variables defined in the
        Exscript.Host objects are preserved.

        @type  filename: str
        @param filename: A file containing a CSV formatted list of hosts.
        """
        for host in get_hosts_from_csv(filename, encoding = encoding):
            self.add_host(host)

    def get_hosts(self):
        """
        Returns Exscript.Host objects for all hosts that are
        included in the order.

        @rtype:  [Exscript.Host]
        @return: A list of hosts.
        """
        return self.hosts
