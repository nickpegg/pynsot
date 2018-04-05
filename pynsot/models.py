# -*- coding: utf-8 -*-

"""
API Model Classes

These resource models are derrived from collections.MutableMapping and, thus,
act like dicts and can instantiate with raw resource output from API as well as
simplifying by providing site_id and (usually) the natural key (cidr, hostname,
etc).
"""

from __future__ import unicode_literals
import abc
import collections
import copy
import urlparse

import coreapi
from pynsot.vendor.slumber.exceptions import HttpClientError, HttpServerError
from pynsot.client import get_api_client

from .exc import NsotHttpError, DoesNotExist


# Default limit of how many Resource objects at a time to ask for
PAGE_LIMIT = 100


def deep_merge(dict_a, dict_b):
    """
    Return a new dict that is dict_b deeply merged into dict_a, meaning any
    nested dicts will also be deeply merged. This is different from the
    standard "shallow" merge where any nested dicts in dict_b simply overwrite
    nested dicts in dict_a.

    :param dict_a:
        The dict to be merged in to

    :param dict_b:
        The dict to merge into dict_a

    :returns:
        A copy of dict_a with dict_b merged into it
    """
    dict_a = copy.deepcopy(dict_a)

    for key, b_val in dict_b.iteritems():
        a_val = dict_a.get(key)

        if isinstance(a_val, dict) and isinstance(b_val, dict):
            dict_a[key] = deep_merge(a_val, b_val)
        else:
            dict_a[key] = b_val

    return dict_a


##jathan
# FIXME(jathan): If we want to keep using this, move it to a util function (or
# nsot-utils?)
# Forklifted from ``drf_yasg.utils.filter_none()``
def filter_none(obj):
    """Remove ``None`` values from tuples, lists or dictionaries. Return other objects as-is.

    :param obj:
    :return: collection with ``None`` values removed
    """
    if obj is None:
        return None
    new_obj = None
    if isinstance(obj, dict):
        new_obj = type(obj)((k, v) for k, v in obj.items() if k is not None and v is not None)
    if isinstance(obj, (list, tuple)):
        new_obj = type(obj)(v for v in obj if v is not None)
    if new_obj is not None and len(new_obj) != len(obj):
        return new_obj  # pragma: no cover
    return obj
##jathan


class Resource(collections.MutableMapping):
    """
    Represents a base NSoT Resource, all other NSoT classes inherit off of this

    Child classes of this class must set a resource which matches the part of
    the API URL that is relevant. Example:
    Device -> /api/devices/ -> resource_name = 'devices'
    """
    __metaclass__ = abc.ABCMeta

    # fields needs to exist here before __init__ is called because of our use
    # of __getattr__/__setattr__. Without this we end up falling into an
    # infinite recursion
    fields = []

    def __init__(self, nsot_client=None, **kwargs):
        # If a nsot client is passed in, use that. Otherwise try looking it up
        # from the class object, or fail gloriously.
        self.nsot_client = self.nsot_client or nsot_client
        if not self.nsot_client:
            raise RuntimeError((
                "You must either call models.init() or supply a "
                "nsot_client to this class"
           ))

        self.initialize_object(obj=kwargs)

    def initialize_object(self, obj=None):
        """
        Figure out what fields exist should exist on this model, set those
        on the internal object representation. If the passed-in obj has that
        key, use it, otherwise default to None.
        """
        self.obj = {}

        if obj is None:
            obj = {}
        else:
            # Get a deep copy to protect against external modifications
            obj = copy.deepcopy(obj)

        for field in self.fields:
            # FIXME(jathan): We need to stop assuming that clients will be
            # site-scoped.
            if field == 'site_id':
                # For now, skip ``site_id`` since a ModelClient.nsot_client
                # object is always scoped to a site
                continue

            default = None
            if field == 'attributes':
                default = {}

            self.obj[field] = obj.get(field, default)

    @classmethod
    def from_dict(cls, obj):
        """
        Given a dict, return an instance.

        :param obj:
            Dictionary representation of an object

        :returns:
            Resource instance
        """
        return cls(**obj)

    # Dict-like access methods
    def __getitem__(self, key):
        return self.obj[key]

    def __setitem__(self, key, value):
        self.obj[key] = value

    def __delitem__(self, key):
        del self.obj[key]

    def __iter__(self):
        return iter(self.obj)

    def __len__(self):
        return len(self.obj)

    # Attribute access methods
    def __getattr__(self, attr):
        try:
            return self.obj[attr]
        except KeyError:
            raise AttributeError("'{}' object has no attribute '{}'".format(
                self.__class__, attr
            ))

    def __setattr__(self, attr, val):
        """
        If an attribute is set that exists in our list of NSoT model fields,
        save it to the internal dict. Otherwise save it to the object itself.
        """
        if attr in self.fields:
            self.obj[attr] = val
        else:
            self.__dict__[attr] = val

    def __repr__(self):
        natural_key = getattr(self, self.natural_key)
        return '<{}: {}>'.format(self.__class__.__name__, natural_key)

    @abc.abstractproperty
    def resource_name(self):
        pass

    @property
    def resource(self):
        """
        Returns the slumber resource to access this NSoT resource
        """
        return getattr(self.nsot_client, self.resource_name)

    def _call_method(self, resource, method_name, *args, **kwargs):
        """
        Calls the given method on the given resource. This exists to provide a
        central location to do handling of common errors that come from these
        responses.

        :param method_name:
            String representation of the method to use, e.g. 'get', 'put'

        :returns:
            Returns the payload from the method call
        """
        method = getattr(resource, method_name.lower())

        try:
            return method(*args, **kwargs)
        except (HttpClientError, HttpServerError) as e:
            self.handle_method_error(e, method_name, (args, kwargs))

    def handle_method_error(self, err, method_name, args):
        try:
            msg = err.response.json()['error']['message']
        except ValueError:
            msg = err.response.text

        # If it's a 404 raise DoesNotExist...
        if err.response.status_code == 404:
            exc_class = DoesNotExist
        else:
            exc_class = NsotHttpError

        raise exc_class(
            'Unable to perform {} on object with args {}: {}'.format(
                method_name,
                args,
                msg
            ),
            response=err.response
        )

    @classmethod
    def get(cls, pk):
        """
        Fetch the object from NSoT by it's primary key or natural key (if
        supported) and return the Resource object that wraps the NSoT object

        """
        r = cls()
        item = r._call_method(r.resource(pk), 'get')
        return cls(**item)

    @classmethod
    def filter(cls, **fields):
        """
        Fetch object(s) from NSoT that have fields that match the given keyword
        args, similar to Django's `filter` method on models.

        :returns:
            A generator of Resource objects representing the results
        """
        fields = copy.deepcopy(fields)
        # Remove attributes since we can't filter on those
        if 'attributes' in fields.keys():
            del fields['attributes']

        r = cls()

        offset = 0
        items = r._call_method(r.resource, 'get', limit=PAGE_LIMIT,
                               offset=offset, **fields)['results']
        while len(items) > 0:
            for item in items:
                yield cls(**item)

            offset += PAGE_LIMIT
            items = r._call_method(r.resource, 'get', limit=PAGE_LIMIT,
                                   offset=offset, **fields)['results']

    @classmethod
    def set_query(cls, query, **fields):
        """
        Performs a set query on the resource and returns a list of class
        instances of objects that match that query

        :returns:
            A generator of Resource objects representing the results
        """
        r = cls()
        fields = copy.deepcopy(fields)
        fields['query'] = query

        # Remove attributes since we can't filter on those
        if 'attributes' in fields.keys():
            del fields['attributes']

        offset = 0
        items = r._call_method(r.resource.query, 'get', limit=PAGE_LIMIT,
                               offset=offset, **fields)['results']
        while len(items) > 0:
            for item in items:
                yield cls(**item)

            offset += PAGE_LIMIT
            items = r._call_method(r.resource.query, 'get', limit=PAGE_LIMIT,
                                   offset=offset, **fields)['results']

    def detail(self, detail_name, **kwargs):
        """
        Fetch a detail view of the object by name, for example 'interfaces' on
        a Device object. This would translate to a GET on
        devices/:id/interfaces/

        Any kwargs passed to this method will get passed along to the detail
        view as query parameters.

        Only supports GET operations right now. Whatever the API endpoint
        returns is what this method returns, since the return values may vary
        from endpoint to endpoint.

        For example, if you are fetching interfaces from a device, you may want
        to do something like this::

            >>> [models.Interface(i) for i in device.detail('interfaces')]

        :param detail_name:
            The name of the detail view, the ":detail" in
            /api/sites/1/:resource/:id/:detail

        :returns:
            The result of the HTTP GET, which may vary between endpoints
        """
        pk = self.obj.get('id')
        if pk is None:
            existing = self.existing_object()
            if existing is not None:
                pk = existing.get('id')

        if not pk:
            raise DoesNotExist

        resource = getattr(self.resource(pk), detail_name)
        return self._call_method(resource, 'get', **kwargs)

    @classmethod
    def create(cls, **kwargs):
        payload = filter_none(kwargs)
        payload.pop('id', None)  # Ditch id explicitly

        self = cls()
        new_obj = self._call_method(self.resource, 'post', payload)

        return new_obj

    def update(self, overwrite=False, **kwargs):
        payload = filter_none(kwargs)
        orig = self.existing_object()
        if not overwrite:
            # We don't use PATCH at all since it doesn't work well. Instead
            # merge our stored object onto the original and PUT that
            # whole enchilada
            payload = deep_merge(orig.obj, payload)

        pk = orig.obj['id']

        # Only PUT the object if it differs from the original
        if payload != orig.obj:
            new_obj = self._call_method(self.resource(pk), 'put', payload)
        else:
            new_obj = payload

        # Store the saved object to make sure we're in-sync
        for k, v in new_obj.iteritems():
            if k in self.fields:
                self.obj[k] = v

        return self.obj

    def save(self, overwrite=False):
        """
        Create or update this resource object. If it doesn't already exist, do
        a POST, if it does, do a PUT or a PATCH depending on whether we're told
        to overwrite the object
        """
        # Leave it up to .create() or .update() to filter None themselves.
        payload = self.obj

        orig = self.existing_object()
        if orig is None:
            new_obj = self.create(**payload)
        else:
            new_obj = self.update(overwrite=overwrite, **payload)

        # Store the saved object to make sure we're in-sync
        for k, v in new_obj.iteritems():
            if k in self.fields:
                self.obj[k] = v

        return self.obj

    def delete(self, **kwargs):
        pk = self.obj.get('id', self.existing_object()['id'])

        self._call_method(self.resource(pk), 'delete', **kwargs)
        self.initialize_object(obj={})

    def existing_object(self):
        """
        Try really hard to get the existing object. First by GETing the object
        by the unique ID if set on this Resource object, then by doing a
        filter() on this object's field values.

        :returns:
            A Resource model object representing the existing object, or None
            if the object doesn't exist
        """
        obj = None

        if self.obj.get('id', 0):
            try:
                obj = self.get(self.obj['id'])
            except HttpClientError as e:
                if e.resonse.status_code != 404:
                    # If this is anything besides a 404, let it bubble up
                    raise e
        else:
            try:
                obj = self.filter(**self.obj).next()
            except StopIteration:
                obj = None

        return obj

    def exists(self):
        """
        Returns True if the object exists in NSoT, False otherwise.
        """
        return self.existing_object() is not None


# THIS IS NOT WORKING YET
class ResourceList(collections.MutableSequence):
    """A list of Resource objects that supports bulk operations."""
    def __init__(self, objects, **kwargs):
        self.objects = objects

    def __iter__(self):
        return self.objects.next()

    @classmethod
    def filter(cls, **fields):
        pass

    @classmethod
    def get(cls, pk):
        pass

    def update(self, overwrite=False, **kwargs):
        pass

    def delete(self, **kwargs):
        pass

    def exists(self):
        return all(o.existing_object() for o in self.objects)


# NYI - Exclude these for now.
EXCLUDE_FROM_SCHEMA = ['authenticate', 'sites', 'users', 'values']

# Used to represent data used to create Resource subclasses dynamically within a
# ModelClient instance.
ModelSchema = collections.namedtuple(
    'ModelSchema', ['resource_name', 'natural_key', 'fields']
)

# Definitions of each API resource for use in generating subclasses.
MODEL_SCHEMAS = [
    ModelSchema(
        resource_name='attributes',
        natural_key='id',
        fields=[
            'id',
            'constraints',
            'description',
            'display',
            'multi',
            'name',
            'required',
            'resource_name',
        ]
    ),
    ModelSchema(
        resource_name='devices',
        natural_key='hostname',
        fields=['id', 'attributes', 'hostname']
    ),
    ModelSchema(
        resource_name = 'interfaces',
        natural_key = 'name_slug',
        fields = [
            'id',
            'addresses',
            'attributes',
            'description',
            'device',
            'mac_address',
            'name',
            'parent',
            'speed',
            'type',

            # Read-only fields
            'device_hostname',
            'name_slug',
            'networks',
            'parent_id',
        ]
    ),
    ModelSchema(
        resource_name = 'circuits',
        natural_key = 'name_slug',
        fields = [
            'id',
            'attributes',
            'endpoint_a',
            'endpoint_z',
            'name',

            # Read-only fields
            'name_slug',
        ]
    ),
    ModelSchema(
        resource_name = 'networks',
        natural_key = 'cidr',
        fields = [
            'id',
            'attributes',
            'cidr',
            'network_address',
            'prefix_length',
            'state',

            # Read-only fields
            'ip_version',
            'is_ip',
            'parent',
            'parent_id',
        ]
    ),
    ModelSchema(
        resource_name = 'protocols',
        natural_key = 'id',
        fields = [
            'id',
            'attributes',
            'auth_string',
            'circuit',
            'description',
            'device',
            'interface',
            'type',
        ]
    ),
    ModelSchema(
        resource_name = 'protocol_types',
        natural_key = 'name',
        fields = [
            'id',
            'description',
            'name',
            'required_attributes',
        ]
    ),
]


class ModelClient(object):
    """Special client that calls NSoT underneath but emits classes."""
    def __init__(self, nsot_client=None, **client_kwargs):
        # If a nsot client is passed in, use that. Otherwise get one!
        if nsot_client is None:
            raw_client = get_api_client(**client_kwargs)
            nsot_client = raw_client.sites(raw_client.default_site)

        self.nsot_client = nsot_client

        # Store the generated model classes on the client instance in case we
        # need to reference them. We need to do this because
        # ``Resource.__subclasses__()`` will have duplicate classes for each time
        # ModelClient is instantiated.
        self.model_classes = []

        # Generate the resource model classes
        self.generate_models()

    # NYI
    def get_schema(self, nsot_client=None):
        if nsot_client is None:
            nsot_client = self.nsot_client

        api_url = nsot_client._store['base_url']
        url = urlparse.urlsplit(api_url)

        schema_url = '{}://{}/schema/'.format(url.scheme, url.netloc)
        schema_client = coreapi.Client()
        schema = schema_client.get(schema_url, format='openapi')

        return schema

    def normalize_resource_name(self, resource_name):
        """
        Normalize a model's resource_name to a suitable class name.

        Example::

            >>> models.generate_class_name('protocol_types')
            'ProtocolType'

        :parma resource_name:
            Plural model resource name

        :returns:
            str
        """
        name = resource_name[:-1].title()  # foos -> Foo
        name = name.replace('_', '') # Foo_Bar -> FooBar
        return bytes(name)

    def generate_models(self):
        """Walk thru MODEL_SCHEMAS and generate resource classes."""
        bases = (Resource,)

        # For each model schema, generate a Resource subclass and attach it to
        # the instance as an attribute (e.g. ``models.Device``).
        for mschema in MODEL_SCHEMAS:
            name = self.normalize_resource_name(mschema.resource_name)
            dict_ = dict(
                nsot_client=self.nsot_client,
                **mschema._asdict()
            )
            cls = type(name, bases, dict_)  # e.g. ``class Foo``
            setattr(self, name, cls)  # e.g. ``self.Foo = Foo``
            self.model_classes.append(cls)


'''
    def _generate_models(self):
        """Auto-generate each resource class."""
        Resource = type(
            'Resource', (_ResourceMeta,), {'nsot_client': self.nsot_client}
        )

        class Attribute(Resource):
            resource_name = 'attributes'
            natural_key = 'id'
            fields = [
                'id',
                'constraints',
                'description',
                'display',
                'multi',
                'name',
                'required',
                'resource_name',
            ]

        class Device(Resource):
            resource_name = 'devices'
            natural_key = 'hostname'
            fields = [
                'id',
                'attributes',
                'hostname',
            ]

        class Interface(Resource):
            resource_name = 'interfaces'
            natural_key = 'name_slug'
            fields = [
                'id',
                'addresses',
                'attributes',
                'description',
                'device',
                'mac_address',
                'name',
                'parent',
                'speed',
                'type',

                # Read-only fields
                'device_hostname',
                'name_slug',
                'networks',
                'parent_id',
            ]

        class Circuit(Resource):
            resource_name = 'circuits'
            natural_key = 'name_slug'
            fields = [
                'id',
                'attributes',
                'endpoint_a',
                'endpoint_z',
                'name',

                # Read-only fields
                'name_slug',
            ]

        class Network(Resource):
            resource_name = 'networks'
            natural_key = 'cidr'
            fields = [
                'id',
                'attributes',
                'cidr',
                'network_address',
                'prefix_length',
                'state',

                # Read-only fields
                'ip_version',
                'is_ip',
                'parent',
                'parent_id',
            ]

        class Protocol(Resource):
            resource_name = 'protocols'
            natural_key = 'id'
            fields = [
                'id',
                'attributes',
                'auth_string',
                'circuit',
                'description',
                'device',
                'interface',
                'type',
            ]

        class ProtocolType(Resource):
            resource_name = 'protocol_types'
            natural_key = 'name'
            fields = [
                'id',
                'description',
                'name',
                'required_attributes',
            ]

        for cls in (Attribute, Device, Interface, Circuit, Network, Protocol,
                    ProtocolType):
            setattr(self, cls.__name__, cls)

    # Individual resource classes for people to use
    class Attribute(Resource):
        resource_name = 'attributes'
        natural_key = 'id'
        fields = [
            'id',
            'constraints',
            'description',
            'display',
            'multi',
            'name',
            'required',
            'resource_name',
        ]

    class Device(Resource):
        resource_name = 'devices'
        natural_key = 'hostname'
        fields = [
            'id',
            'attributes',
            'hostname',
        ]

    class Interface(Resource):
        resource_name = 'interfaces'
        natural_key = 'name_slug'
        fields = [
            'id',
            'addresses',
            'attributes',
            'description',
            'device',
            'mac_address',
            'name',
            'parent',
            'speed',
            'type',

            # Read-only fields
            'device_hostname',
            'name_slug',
            'networks',
            'parent_id',
        ]

    class Circuit(Resource):
        resource_name = 'circuits'
        natural_key = 'name_slug'
        fields = [
            'id',
            'attributes',
            'endpoint_a',
            'endpoint_z',
            'name',

            # Read-only fields
            'name_slug',
        ]

    class Network(Resource):
        resource_name = 'networks'
        natural_key = 'cidr'
        fields = [
            'id',
            'attributes',
            'cidr',
            'network_address',
            'prefix_length',
            'state',

            # Read-only fields
            'ip_version',
            'is_ip',
            'parent',
            'parent_id',
        ]

    class Protocol(Resource):
        resource_name = 'protocols'
        natural_key = 'id'
        fields = [
            'id',
            'attributes',
            'auth_string',
            'circuit',
            'description',
            'device',
            'interface',
            'type',
        ]

    class ProtocolType(Resource):
        resource_name = 'protocol_types'
        natural_key = 'name'
        fields = [
            'id',
            'description',
            'name',
            'required_attributes',
        ]
'''
