import pytest

from .fixtures import client, config, site, site_client  # noqa

from pynsot import exc, models as client_models


@pytest.fixture  # noqa
def nsot(site_client):
    return site_client.sites(site_client.default_site)


@pytest.fixture  # noqa
def models(nsot):
    return client_models.ModelClient(nsot_client=nsot)


@pytest.fixture
def base_attributes(models):
    attributes = []
    for dev_attr in ('role', 'vendor'):
        attr = models.Attribute.from_dict({
            'name': dev_attr,
            'resource_name': 'Device',
        })
        attr.save()
        attributes.append(attr)

    return attributes


@pytest.fixture
def device(models, base_attributes):
    d = models.Device.from_dict({
        'hostname': 'dev1-foo01',
        'attributes': {
            'role': 'foo',
            'vendor': 'potato',
        }
    })
    d.save()
    return d


@pytest.fixture
def interface(models, device):
    i = models.Interface.from_dict({
        'device': device.id,
        'name': 'Ethernet1/1',
    })
    i.save()
    return i


@pytest.fixture
def circuit(models, device, interface):
    other_interface = models.Interface.from_dict({
        'device': device.id,
        'name': 'Ethernet1/2',
    })
    other_interface.save()

    circuit = models.Circuit.from_dict({
        'endpoint_a': interface.id,
        'ednpoint_z': other_interface.id,
    })
    circuit.save()

    return circuit


@pytest.fixture
def network(models):
    net = models.Network.from_dict({'cidr': '10.0.0.0/8'})
    net.save()
    return net


@pytest.fixture
def protocol_type(models):
    t = models.ProtocolType.from_dict({
        'name': 'bgp',
        'description': 'Border Gateway Protocol',
    })
    t.save()
    return t


@pytest.fixture
def protocol(models, protocol_type, device, interface):
    p = models.Protocol.from_dict({
        'type': protocol_type.id,
        'device': device.id,
        'interface': interface.id,
        'description': 'My cool circuit'
    })
    p.save()
    return p


def test_deep_merge():
    a = {
        'foo': {
            'hello': 'world',
            'oh': 'no',     # Should not get clobbered by b's foo
        },
        'bar': 1,
        'baz': 3,   # Should remain untouched
    }
    b = {
        'bar': 5,   # Should update a's bar
        'foo': {
            'hello': 'jathy',
        },
        'wowie': 'zowie',   # Doesn't exist in a
    }

    c = client_models.deep_merge(a, b)
    assert c['baz'] == 3
    assert c['foo']['hello'] == 'jathy'
    assert c['foo']['oh'] == 'no'
    assert c['bar'] == 5


class TestBasics(object):
    """
    Bunch of basic tests using our friend, the noble Device
    """
    @pytest.fixture
    def bar_device(self, nsot, base_attributes):
        return nsot.devices.post({
            'hostname': 'dev1-bar01',
            'attributes': {
                'role': 'bar',
                'vendor': 'potato',
            }
        })

    def test_get(self, models, device):
        d = models.Device.get('dev1-foo01')

        assert d.obj['hostname'] == 'dev1-foo01'
        assert d.obj['attributes']['role'] == 'foo'

    def test_filter(self, models, device, bar_device):
        devices = list(models.Device.filter(hostname='dev1-foo01'))

        assert len(devices) == 1

        d = devices[0]
        assert d.obj['hostname'] == 'dev1-foo01'
        assert d.obj['attributes']['role'] == 'foo'

    def test_create(self, models):
        obj = models.Device.create(hostname='hotness')
        assert obj['hostname'] == 'hotness'

    def test_update(self, models, device):
        dev = models.Device.get(device['hostname'])
        dev.update(hostname='nick')
        assert dev.hostname == 'nick'

        dev2 = models.Device.get('nick')
        assert dev.obj == dev2.obj

    def test_set_query(self, models, device, bar_device):
        devices = list(models.Device.set_query('role=bar'))

        assert len(devices) == 1

        d = devices[0]
        assert d.obj['hostname'] == 'dev1-bar01'
        print(d.obj)
        assert d.obj['attributes']['role'] == 'bar'

    def test_set_query_with_fields(self, models, device, bar_device):
        """
        Ensure we can do a set query and pass in fields to filter on as well
        """
        metro_devices = list(models.Device.set_query('vendor=potato'))
        assert len(metro_devices) == 2

        devices = list(models.Device.set_query(
            'vendor=potato',
            hostname='dev1-foo01'
        ))
        assert len(devices) == 1
        assert devices[0].obj['hostname'] == 'dev1-foo01'

    def test_detail(self, models, device):
        """
        Simple test of Resource.detail(), set an interface on device and ensure
        that the interface is returned by Device.detail('interfaces').

        Thoroughly testing this method is hard since there are many detail
        routes we'd have to enumerate across all the resources.
        """
        interface = models.Interface.from_dict({
            'name': 'ethernet1/3',
            'device': device.obj['id'],
        })
        interface.save()

        interfaces = device.detail('interfaces')
        objects = map(models.Interface.from_dict, interfaces)
        assert objects == [interface]

    def test_detail_unsaved(self, models):
        """
        detail() throws a exc.DoesNotExist if it's called on something that's not
        persisted in NSoT, such as an unsaved resource.
        """
        device = models.Device.from_dict({'hostname': 'blah'})

        with pytest.raises(exc.DoesNotExist):
            device.detail('interfaces')

        device.save()
        device.detail('interfaces')     # Should not throw an exception

    def test_save_new(self, models):
        d = models.Device()
        d['hostname'] = 'blah'
        d.save()

        saved = models.Device.get(d['id'])

        assert d.obj == saved.obj
        assert saved['hostname'] == 'blah'

    def test_save_existing(self, models, device):
        """
        With the defaults, if we call save() on a Device that already exists,
        any fields that we don't specify should not be overwritten
        """
        d = models.Device()
        d.obj['hostname'] = 'dev1-foo01'
        d.obj['attributes']['role'] = 'foo'
        assert d.exists()

        d.save()
        saved = models.Device.get('dev1-foo01')

        assert d.obj == saved.obj
        assert saved.obj['hostname'] == 'dev1-foo01'
        assert saved.obj['attributes'].get('role') == 'foo'
        assert saved.obj['attributes'].get('vendor') == 'potato'

    def test_save_existing_overwrite(self, models, device):
        """
        If we pass overwrite=True to save() when a Device already exists and
        we don't set some fields, the fields that we don't set should be wiped
        out
        """
        d = models.Device.get('dev1-foo01')
        assert d.exists()

        d.obj['hostname'] = 'dev1-blah01'
        d.obj['attributes'] = {'role': 'blah'}
        d.save(overwrite=True)

        saved = models.Device.get(d.obj['id'])

        assert d.obj == saved.obj

        # The vendor in the original object should have been wiped out
        assert saved.obj['hostname'] == 'dev1-blah01'
        assert saved.obj['attributes'] == {'role': 'blah'}

    def test_delete(self, models, device):
        d = models.Device.get('dev1-foo01')
        assert d.exists()

        d.delete()

        assert not d.exists()
        with pytest.raises(exc.NsotHttpError):
            models.Device.get('dev1-foo01')

    def test_exists_by_id(self, models, device):
        d = models.Device.from_dict({'id': device['id']})
        assert d.exists()

    def test_exists_by_payload(self, models, device):
        d = models.Device.from_dict({'hostname': device['hostname']})
        assert d.exists()

    def test_access_as_dict(self, models):
        d = models.Device()
        d.obj['hostname'] = 'blah'
        assert d['hostname'] == 'blah'

        d['hostname'] = 'ohno'
        assert d.obj['hostname'] == 'ohno'

        del d['hostname']
        assert d.obj.get('hostname', None) is None

    def test_attribute_access(self, models):
        d = models.Device()

        d.obj['hostname'] = 'blah'
        assert d.hostname == 'blah'

        d.hostname = 'ohno'
        assert d.obj['hostname'] == 'ohno'

        d.attributes['whee'] = 'awesome'
        assert d.obj['attributes']['whee'] == 'awesome'

        d.foobar = 'wowie'
        assert 'foobar' not in d.obj.keys()


def test_get_filter_return_the_same_fields(models, base_attributes, device, interface,
                                           circuit, network, protocol,
                                           protocol_type):
    """
    Resource.get() and Resource.filter() should return Resource objects with
    the same fields.
    """
    # Generated model classes are stored at ``ModelClient.model_classes``.
    for klass in models.model_classes:
        filter_obj = klass.filter().next()
        get_obj = klass.get(filter_obj.id)
        filter_keys = sorted(filter_obj.obj.keys())
        get_keys = sorted(get_obj.obj.keys())

        assert filter_keys == get_keys


def test_filter_and_set_query_return_everything(models, base_attributes):
    """
    After changing Resource.filter() and Resource.set_query() to return
    iterators which handle pagination, ensure that these two methods still
    return all the things.
    """
    # First, create enough Devices to require pagination
    hostname_tmpl = 'dev1a-foo{}'
    num_devices = client_models.PAGE_LIMIT + 1
    for i in range(1, num_devices + 1):
        device = models.Device.from_dict({
            'hostname': hostname_tmpl.format(i),
            'attributes': {'role': 'foo'},
        })
        device.save()

    devices = models.Device.filter()
    assert len(list(devices)) == num_devices

    devices = models.Device.set_query('role=foo')
    assert len(list(devices)) == num_devices
