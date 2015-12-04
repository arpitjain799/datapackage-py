from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals


import os
import csv
import json
import requests
import six

from .exceptions import (
    ResourceError
)


class Resource(object):
    '''Base class for all Data Package's resource types.

    This classes will usually be created by :class:`DataPackage`, and not by
    you. If you need to create one, use the :func:`Resource.load` factory
    method.

    The resources' attributes should only be altered through the
    :data:`metadata` dict.
    '''

    @classmethod
    def load(cls, metadata, default_base_path=None):
        '''Factory method that loads the resource described in ``metadata``.

        It'll first try to load the resource defined in ``metadata`` as a
        :class:`TabularResource`. If that fails, it'll fall back to loading it
        as a :class:`Resource`.

        Args:
            metadata (dict): The dict with the resource's metadata
            default_base_path (str, optional): The base path to be used in case
                the resource's data is in the local disk. Usually this would be
                the base path of the `datapackage.json` this resource is in.

        Returns:
            Resource: The returned resource's class will depend on the type of
                resource. If it was tabular, a :class:`TabularResource` will be
                returned, otherwise, it'll be a :class:`Resource`.

        Raises:
            ResourceError: If the resource couldn't be loaded.
        '''
        try:
            resource = TabularResource(metadata, default_base_path)
        except ValueError:
            resource = cls(metadata, default_base_path)
        return resource

    def __init__(self, metadata, default_base_path=None):
        self._metadata = metadata
        self._base_path = self.metadata.get('base', default_base_path)
        self._data = self._parse_data(metadata)

    @property
    def metadata(self):
        '''dict: The metadata this resource was created with.'''
        return self._metadata

    @property
    def data(self):
        '''Returns this resource's data.

        The data should not be changed.

        Returns:
            str: This resource's data.

        Raises:
            ResourceError: If the resource couldn't be loaded. This will only
                happen if you've changed the data pointed by :data:`metadata`.
        '''
        if self._metadata_data_has_changed(self.metadata):
            self._data = self._parse_data(self.metadata)
        return self._data

    @property
    def local_data_path(self):
        '''str: The absolute local path for the data, if it exists locally.'''
        path = self._absolute_path(self.metadata.get('path'))
        if path and os.path.isfile(path):
            return path

    def _metadata_data_has_changed(self, metadata):
        metadata_data_ids = self._metadata_data_ids(metadata)
        return metadata_data_ids != self._original_metadata_data_ids

    def _metadata_data_ids(self, metadata):
        return {
            'data_id': id(metadata.get('data')),
            'data_path_id': id(metadata.get('path')),
            'data_url_id': id(metadata.get('url'))
        }

    def _parse_data(self, metadata):
        self._original_metadata_data_ids = self._metadata_data_ids(metadata)
        return self._load_data(metadata)

    def _load_data(self, metadata):
        inline_data = metadata.get('data')
        data_path = metadata.get('path')
        data_url = metadata.get('url')
        error = None

        data = inline_data

        if data is None and data_path:
            try:
                if self.local_data_path:
                    data = self._load_data_from_path(self.local_data_path)
                else:
                    url = self._absolute_path(data_path)
                    data = self._load_data_from_url(url)
            except ResourceError as e:
                error = e

        if data is None and data_url:
            try:
                data = self._load_data_from_url(data_url)
            except ResourceError as e:
                if not error:
                    error = e

        if data is None and error:
            raise error

        return data

    def _load_data_from_path(self, path):
        try:
            with open(path, 'r') as f:
                data = f.read()
                if six.PY2:
                    data = unicode(data, 'utf-8')
                return data
        except IOError as e:
            six.raise_from(ResourceError(e), e)

    def _load_data_from_url(self, url):
        try:
            req = requests.get(url)
            req.raise_for_status()
            return req.text
        except requests.exceptions.RequestException as e:
            six.raise_from(ResourceError(e), e)

    def _absolute_path(self, path):
        if path is None or self._base_path is None:
            return path
        return os.path.join(self._base_path, path)


class TabularResource(Resource):
    '''Subclass of :class:`Resource` that deals with tabular data.

    It currently only supports CSVs.
    '''

    def _parse_data(self, metadata):
        '''Parses the data defined in ``metadata``

        Returns:
            tuple of dicts: The parsed rows of this resource.

        Raises:
            ValueError: If the data isn't tabular. We consider tabular data as
                a ``list``, ``tuple``, ``CSV`` or ``JSON``. If it's a ``JSON``,
                its root content must be an array.
        '''
        data = super(TabularResource, self)._parse_data(metadata)

        if isinstance(data, six.string_types):
            try:
                data = json.loads(data)
            except ValueError:
                data = [row for row in _csv_dictreader(six.StringIO(data))]
                if not data:
                    data = None

        self._raise_if_isnt_tabular_data(data)

        return data

    def _raise_if_isnt_tabular_data(self, data):
        tabular_types = (
            list,
            tuple,
        )
        valid = False

        for tabular_type in tabular_types:
            if isinstance(data, tabular_type):
                valid = True
                break

        if not valid:
            types_str = ', '.join([t.__name__ for t in tabular_types])
            msg = 'Expected data type to be any of \'{0}\' but it was \'{1}\''
            raise ValueError(msg.format(types_str, type(data).__name__))


if six.PY2:
    def _csv_dictreader(data, dialect=csv.excel, **kwargs):
        '''Read text stream (unicode on Py2.7) as CSV.'''

        def iterenc_utf8(data):
            for line in data:
                yield line.encode('utf-8')

        reader = csv.DictReader(iterenc_utf8(data), dialect=dialect, **kwargs)
        for row in reader:
            yield dict([(unicode(k, 'utf-8'), unicode(v, 'utf-8'))
                        for (k, v) in row.items()])
else:
    _csv_dictreader = csv.DictReader
