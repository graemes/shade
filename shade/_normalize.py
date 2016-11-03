# Copyright (c) 2015 Hewlett-Packard Development Company, L.P.
# Copyright (c) 2016 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import munch
import six

_IMAGE_FIELDS = (
    'checksum',
    'container_format',
    'created_at',
    'direct_url',
    'disk_format',
    'file',
    'id',
    'min_disk',
    'min_ram',
    'name',
    'owner',
    'size',
    'status',
    'tags',
    'updated_at',
    'virtual_size',
)

_SERVER_FIELDS = (
    'accessIPv4',
    'accessIPv6',
    'addresses',
    'adminPass',
    'created',
    'key_name',
    'metadata',
    'networks',
    'private_v4',
    'public_v4',
    'public_v6',
    'security_groups',
    'status',
    'updated',
    'user_id',
)


def _to_bool(value):
    if isinstance(value, six.string_types):
        if not value:
            return False
        prospective = value.lower().capitalize()
        return prospective == 'True'
    return bool(value)


def _pop_int(resource, key):
    return int(resource.pop(key, 0) or 0)


def _pop_float(resource, key):
    return float(resource.pop(key, 0) or 0)


def _pop_or_get(resource, key, default, strict):
    if strict:
        return resource.pop(key, default)
    else:
        return resource.get(key, default)


class Normalizer(object):
    '''Mix-in class to provide the normalization functions.

    This is in a separate class just for on-disk source code organization
    reasons.
    '''

    def _normalize_flavors(self, flavors):
        """ Normalize a list of flavor objects """
        ret = []
        for flavor in flavors:
            ret.append(self._normalize_flavor(flavor))
        return ret

    def _normalize_flavor(self, flavor):
        """ Normalize a flavor object """
        new_flavor = munch.Munch()

        # Copy incoming group because of shared dicts in unittests
        flavor = flavor.copy()

        # Discard noise
        flavor.pop('links', None)
        flavor.pop('NAME_ATTR', None)
        flavor.pop('HUMAN_ID', None)
        flavor.pop('human_id', None)

        ephemeral = int(_pop_or_get(
            flavor, 'OS-FLV-EXT-DATA:ephemeral', 0, self.strict_mode))
        ephemeral = flavor.pop('ephemeral', ephemeral)
        is_public = _to_bool(_pop_or_get(
            flavor, 'os-flavor-access:is_public', True, self.strict_mode))
        is_public = _to_bool(flavor.pop('is_public', is_public))
        is_disabled = _to_bool(_pop_or_get(
            flavor, 'OS-FLV-DISABLED:disabled', False, self.strict_mode))
        extra_specs = flavor.pop('extra_specs', {})

        new_flavor['location'] = self.current_location
        new_flavor['id'] = flavor.pop('id')
        new_flavor['name'] = flavor.pop('name')
        new_flavor['is_public'] = is_public
        new_flavor['is_disabled'] = is_disabled
        new_flavor['ram'] = _pop_int(flavor, 'ram')
        new_flavor['vcpus'] = _pop_int(flavor, 'vcpus')
        new_flavor['disk'] = _pop_int(flavor, 'disk')
        new_flavor['ephemeral'] = ephemeral
        new_flavor['swap'] = _pop_int(flavor, 'swap')
        new_flavor['rxtx_factor'] = _pop_float(flavor, 'rxtx_factor')

        new_flavor['properties'] = flavor.copy()
        new_flavor['extra_specs'] = extra_specs

        # Backwards compat with nova - passthrough values
        if not self.strict_mode:
            for (k, v) in new_flavor['properties'].items():
                new_flavor.setdefault(k, v)

        return new_flavor

    def _normalize_images(self, images):
        ret = []
        for image in images:
            ret.append(self._normalize_image(image))
        return ret

    def _normalize_image(self, image):
        new_image = munch.Munch(
            location=self._get_current_location(project_id=image.get('owner')))

        properties = image.pop('properties', {})
        visibility = image.pop('visibility', None)
        protected = _to_bool(image.pop('protected', False))

        if visibility:
            is_public = (visibility == 'public')
        else:
            is_public = image.pop('is_public', False)
            visibility = 'public' if is_public else 'private'

        for field in _IMAGE_FIELDS:
            new_image[field] = image.pop(field, None)
        for field in ('min_ram', 'min_disk', 'size', 'virtual_size'):
            new_image[field] = _pop_int(new_image, field)
        new_image['is_protected'] = protected
        new_image['locations'] = image.pop('locations', [])

        for key, val in image.items():
            properties.setdefault(key, val)
        new_image['properties'] = properties
        new_image['visibility'] = visibility
        new_image['is_public'] = is_public

        # Backwards compat with glance
        if not self.strict_mode:
            for key, val in properties.items():
                new_image[key] = val
            new_image['protected'] = protected
        return new_image

    def _normalize_secgroups(self, groups):
        """Normalize the structure of security groups

        This makes security group dicts, as returned from nova, look like the
        security group dicts as returned from neutron. This does not make them
        look exactly the same, but it's pretty close.

        :param list groups: A list of security group dicts.

        :returns: A list of normalized dicts.
        """
        ret = []
        for group in groups:
            ret.append(self._normalize_secgroup(group))
        return ret

    def _normalize_secgroup(self, group):

        ret = munch.Munch()
        # Copy incoming group because of shared dicts in unittests
        group = group.copy()

        rules = self._normalize_secgroup_rules(
            group.pop('security_group_rules', group.pop('rules', [])))
        project_id = group.pop('tenant_id', '')
        project_id = group.pop('project_id', project_id)

        ret['location'] = self._get_current_location(project_id=project_id)
        ret['id'] = group.pop('id')
        ret['name'] = group.pop('name')
        ret['security_group_rules'] = rules
        ret['description'] = group.pop('description')
        ret['properties'] = group

        # Backwards compat with Neutron
        if not self.strict_mode:
            ret['tenant_id'] = project_id
            ret['project_id'] = project_id
            for key, val in ret['properties'].items():
                ret.setdefault(key, val)

        return ret

    def _normalize_secgroup_rules(self, rules):
        """Normalize the structure of nova security group rules

        Note that nova uses -1 for non-specific port values, but neutron
        represents these with None.

        :param list rules: A list of security group rule dicts.

        :returns: A list of normalized dicts.
        """
        ret = []
        for rule in rules:
            ret.append(self._normalize_secgroup_rule(rule))
        return ret

    def _normalize_secgroup_rule(self, rule):
        ret = munch.Munch()
        # Copy incoming rule because of shared dicts in unittests
        rule = rule.copy()

        ret['id'] = rule.pop('id')
        ret['direction'] = rule.pop('direction', 'ingress')
        ret['ethertype'] = rule.pop('ethertype', 'IPv4')
        port_range_min = rule.get(
            'port_range_min', rule.pop('from_port', None))
        if port_range_min == -1:
            port_range_min = None
        if port_range_min is not None:
            port_range_min = int(port_range_min)
        ret['port_range_min'] = port_range_min
        port_range_max = rule.pop(
            'port_range_max', rule.pop('to_port', None))
        if port_range_max == -1:
            port_range_max = None
        if port_range_min is not None:
            port_range_min = int(port_range_min)
        ret['port_range_max'] = port_range_max
        ret['protocol'] = rule.pop('protocol', rule.pop('ip_protocol', None))
        ret['remote_ip_prefix'] = rule.pop(
            'remote_ip_prefix', rule.pop('ip_range', {}).get('cidr', None))
        ret['security_group_id'] = rule.pop(
            'security_group_id', rule.pop('parent_group_id', None))
        ret['remote_group_id'] = rule.pop('remote_group_id', None)
        project_id = rule.pop('tenant_id', '')
        project_id = rule.pop('project_id', project_id)
        ret['location'] = self._get_current_location(project_id=project_id)
        ret['properties'] = rule

        # Backwards compat with Neutron
        if not self.strict_mode:
            ret['tenant_id'] = project_id
            ret['project_id'] = project_id
            for key, val in ret['properties'].items():
                ret.setdefault(key, val)
        return ret

    def _normalize_servers(self, servers):
        # Here instead of _utils because we need access to region and cloud
        # name from the cloud object
        ret = []
        for server in servers:
            ret.append(self._normalize_server(server))
        return ret

    def _normalize_server(self, server):
        ret = munch.Munch()
        # Copy incoming server because of shared dicts in unittests
        server = server.copy()

        server.pop('links', None)
        server.pop('NAME_ATTR', None)
        server.pop('HUMAN_ID', None)
        server.pop('human_id', None)

        ret['id'] = server.pop('id')
        ret['name'] = server.pop('name')

        server['flavor'].pop('links', None)
        ret['flavor'] = server.pop('flavor')

        # OpenStack can return image as a string when you've booted
        # from volume
        if str(server['image']) != server['image']:
            server['image'].pop('links', None)
        ret['image'] = server.pop('image')

        project_id = server.pop('tenant_id', '')
        project_id = server.pop('project_id', project_id)

        az = _pop_or_get(
            server, 'OS-EXT-AZ:availability_zone', None, self.strict_mode)
        ret['location'] = self._get_current_location(
            project_id=project_id, zone=az)

        # Ensure volumes is always in the server dict, even if empty
        ret['volumes'] = _pop_or_get(
            server, 'os-extended-volumes:volumes_attached',
            [], self.strict_mode)

        config_drive = server.pop('config_drive', False)
        ret['has_config_drive'] = _to_bool(config_drive)

        host_id = server.pop('hostId', None)
        ret['host_id'] = host_id

        ret['progress'] = _pop_int(server, 'progress')

        # Leave these in so that the general properties handling works
        ret['disk_config'] = _pop_or_get(
            server, 'OS-DCF:diskConfig', None, self.strict_mode)
        for key in (
                'OS-EXT-STS:power_state',
                'OS-EXT-STS:task_state',
                'OS-EXT-STS:vm_state',
                'OS-SRV-USG:launched_at',
                'OS-SRV-USG:terminated_at'):
            short_key = key.split(':')[1]
            ret[short_key] = _pop_or_get(server, key, None, self.strict_mode)

        for field in _SERVER_FIELDS:
            ret[field] = server.pop(field, None)
        ret['interface_ip'] = ''

        ret['properties'] = server.copy()

        # Backwards compat
        if not self.strict_mode:
            ret['hostId'] = host_id
            ret['config_drive'] = config_drive
            ret['project_id'] = project_id
            ret['tenant_id'] = project_id
            ret['region'] = self.region_name
            ret['cloud'] = self.name
            ret['az'] = az
            for key, val in ret['properties'].items():
                ret.setdefault(key, val)
        return ret

    def _normalize_floating_ips(self, ips):
        """Normalize the structure of floating IPs

        Unfortunately, not all the Neutron floating_ip attributes are available
        with Nova and not all Nova floating_ip attributes are available with
        Neutron.
        This function extract attributes that are common to Nova and Neutron
        floating IP resource.
        If the whole structure is needed inside shade, shade provides private
        methods that returns "original" objects (e.g.
        _neutron_allocate_floating_ip)

        :param list ips: A list of Neutron floating IPs.

        :returns:
            A list of normalized dicts with the following attributes::

            [
              {
                "id": "this-is-a-floating-ip-id",
                "fixed_ip_address": "192.0.2.10",
                "floating_ip_address": "198.51.100.10",
                "network": "this-is-a-net-or-pool-id",
                "attached": True,
                "status": "ACTIVE"
              }, ...
            ]

        """
        return [
            self._normalize_floating_ip(ip) for ip in ips
        ]

    def _normalize_floating_ip(self, ip):
        ret = munch.Munch()

        # Copy incoming floating ip because of shared dicts in unittests
        ip = ip.copy()

        fixed_ip_address = ip.pop('fixed_ip_address', ip.pop('fixed_ip', None))
        floating_ip_address = ip.pop('floating_ip_address', ip.pop('ip', None))
        network_id = ip.pop(
            'floating_network_id', ip.pop('network', ip.pop('pool', None)))
        project_id = ip.pop('tenant_id', '')
        project_id = ip.pop('project_id', project_id)

        instance_id = ip.pop('instance_id', None)
        router_id = ip.pop('router_id', None)
        id = ip.pop('id')
        port_id = ip.pop('port_id', None)

        if self._use_neutron_floating():
            attached = bool(port_id)
            status = ip.pop('status', 'UNKNOWN')
        else:
            attached = bool(instance_id)
            # In neutron's terms, Nova floating IPs are always ACTIVE
            status = 'ACTIVE'

        ret = munch.Munch(
            attached=attached,
            fixed_ip_address=fixed_ip_address,
            floating_ip_address=floating_ip_address,
            id=id,
            location=self._get_current_location(project_id=project_id),
            network=network_id,
            port=port_id,
            router=router_id,
            status=status,
            properties=ip.copy(),
        )
        # Backwards compat
        if not self.strict_mode:
            ret['port_id'] = port_id
            ret['router_id'] = router_id
            ret['project_id'] = project_id
            ret['tenant_id'] = project_id
            ret['floating_network_id'] = network_id,
            for key, val in ret['properties'].items():
                ret.setdefault(key, val)

        return ret
